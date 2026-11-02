"""Bounded HTTPS GET only. Pin public DNS addresses; no cookies, proxies or redirects."""
import http.client
import ipaddress
import json
import os
import socket
import ssl
import time
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit

from research_privacy import ApprovedQuery, words


class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.hidden = 0; self.main_parts=[]; self.in_main=0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'svg','nav','header','footer'): self.hidden += 1
        if tag in ('main','article'):self.in_main+=1
        if not self.hidden and tag in ('p','h1','h2','h3','h4','li','section','tr'):
            self.parts.append('\n')
            if self.in_main:self.main_parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg','nav','header','footer'): self.hidden = max(0, self.hidden - 1)
        if tag in ('main','article'):self.in_main=max(0,self.in_main-1)

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)
            if self.in_main:self.main_parts.append(value)


class StructuredRecipe(HTMLParser):
    """Read schema.org recipe JSON as data only; never execute any script."""
    def __init__(self):super().__init__();self.capture=False;self.buffer=[];self.records=[];self.length=0
    def handle_starttag(self,tag,attrs):
        if tag=='script' and dict(attrs).get('type','').lower()=='application/ld+json':self.capture=True;self.buffer=[];self.length=0
    def handle_data(self,data):
        if self.capture and self.length<128000:self.buffer.append(data[:128000-self.length]);self.length+=len(data)
    def handle_endtag(self,tag):
        if tag=='script' and self.capture:
            self.capture=False
            try:self.records.append(json.loads(''.join(self.buffer)))
            except (ValueError,RecursionError):pass


def recipe_text(raw):
    parser=StructuredRecipe();parser.feed(raw)
    pending=list(parser.records);visited=0
    while pending and visited<256:
        node=pending.pop(0);visited+=1
        if isinstance(node,list):pending.extend(node[:40]);continue
        if not isinstance(node,dict):continue
        types=node.get('@type',[]);types=[types] if isinstance(types,str) else types if isinstance(types,list) else []
        if 'Recipe' in types:
            lines=['Recipe: '+str(node.get('name',''))[:200]]
            for key in ('recipeYield','prepTime','cookTime','totalTime'):
                if node.get(key):lines.append(key+': '+str(node[key])[:200])
            ingredients=node.get('recipeIngredient',[])
            if isinstance(ingredients,list):lines+=['Ingredients: '+str(x)[:200] for x in ingredients[:40]]
            steps=node.get('recipeInstructions',[]);steps=[steps] if isinstance(steps,str) else steps
            for step in steps[:25] if isinstance(steps,list) else []:
                if isinstance(step,str):lines.append('Step: '+step[:600])
                elif isinstance(step,dict):
                    if step.get('text'):lines.append('Step: '+str(step['text'])[:600])
                    children=step.get('itemListElement',[])
                    for sub in children[:12] if isinstance(children,list) else []:
                        if isinstance(sub,dict) and sub.get('text'):lines.append('Step: '+str(sub['text'])[:600])
            return '\n'.join(lines)[:10000]
        pending.extend(v for v in node.values() if isinstance(v,(dict,list)))
    return ''


def audit(event,**value):
    path=os.environ.get('RESEARCH_AUDIT_PATH')
    if path:
        fd=os.open(path,os.O_WRONLY|os.O_APPEND|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'a') as out:out.write(json.dumps({'event':event,'time':time.time(),**value})+'\n')


def target(url, hosts, resolve=socket.getaddrinfo):
    p = urlsplit(url)
    if (p.scheme != 'https' or (hosts is not None and p.hostname not in hosts) or p.username or p.password or
            p.port not in (None, 443) or p.fragment or not readable_url(url) or len(url) > 2048 or
            any(ord(c) < 33 for c in url)):
        raise ValueError('Public URL outside configured source policy')
    addresses = list(dict.fromkeys(r[4][0] for r in resolve(p.hostname, 443, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(ip).is_global or getattr(ipaddress.ip_address(ip),'sixtofour',None) or getattr(ipaddress.ip_address(ip),'teredo',None) for ip in addresses):
        raise ValueError('Non-public destination refused')
    return p, addresses[0]


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        sock = socket.create_connection((self.address, 443), self.timeout)
        try: self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close(); raise


def _get(url, hosts, limit=768000, redirects=0):
    p, ip = target(url, hosts)
    start = time.monotonic()
    conn = PinnedHTTPS(p.hostname, ip, 10)
    try:
        conn.request('GET', p.path + ('?' + p.query if p.query else '') or '/',
                     headers={'User-Agent': 'SMARTINIS-Research/0.1', 'Accept': 'text/html,application/json,text/plain', 'Accept-Encoding': 'identity'})
        response = conn.getresponse()
        if response.status in (301,302,303,307,308):
            if redirects>=3:raise ValueError('Source redirect limit')
            from urllib.parse import urljoin
            next_url=urljoin(url,response.getheader('Location',''))
            conn.close()
            return _get(next_url,hosts,limit,redirects+1)
        if response.status != 200: raise ValueError('Source unavailable')
        kind = response.getheader('Content-Type', '').split(';')[0].lower()
        if kind not in ('text/html', 'text/plain', 'application/json'): raise ValueError('Unsupported source format')
        if response.getheader('Content-Encoding', 'identity') != 'identity': raise ValueError('Encoded source refused')
        chunks = []; count = 0; partial=False
        while True:
            if time.monotonic() - start > 20: raise TimeoutError('Source read timeout')
            data = response.read1(min(16384, limit + 1 - count))
            if not data: break
            chunks.append(data); count += len(data)
            if count > limit:partial=True;break
        return b''.join(chunks)[:limit].decode('utf-8', errors='replace'), kind+(';partial' if partial else '')
    finally: conn.close()


def get(url, hosts=None, limit=768000, seconds=25):
    from research_bounds import bounded
    return bounded(_get,(url,hosts,limit),min(25,seconds))


def readable_url(url):
    try:
        p=urlsplit(url)
        if not p.hostname or '%' in p.hostname or '.' not in p.hostname:return False
        if p.hostname.endswith(('.localhost','.local','.internal','.onion')):return False
        if len(p.query)>512:return False
        import re
        from urllib.parse import parse_qs,unquote
        path=p.path;query=p.query
        for _ in range(3):path=unquote(path);query=unquote(query)
        if re.search(r'/(login|logout|signout|signin|checkout|delete|unsubscribe|admin)(/|$)',path,re.I):return False
        if any(k.lower() in ('token','access_token','api_key','apikey','password','auth','session','action','cmd','command','do','method','operation','delete','submit','execute') for k in parse_qs(query)):return False
        return True
    except (ValueError,TypeError):return False


def _local_search(query,engines):
    conn=http.client.HTTPConnection('127.0.0.1',8888,timeout=12)
    try:
        conn.request('GET','/search?'+urlencode({'q':query,'format':'json','engines':engines,'language':'en'}),headers={'Accept':'application/json'})
        response=conn.getresponse()
        if response.status!=200 or response.getheader('Content-Type','').split(';')[0]!='application/json':
            raise ValueError('Local search JSON unavailable')
        raw=response.read(384001)
        if len(raw)>384000:raise ValueError('Search result too large')
        return raw.decode('utf-8'),'application/json'
    finally:conn.close()


STOP_WORDS=frozenset('the a an of in on at for and or to is are was were what when which how latest current official best practices date release stable available website'.split())


class PublicWeb:
    def __init__(self,endpoint,source_hosts=None,engines='brave,yahoo,wikipedia'):
        p=urlsplit(endpoint)
        self.local=endpoint=='http://127.0.0.1:8888/search'
        if not self.local and (p.scheme!='https' or not p.hostname or p.query or p.fragment or p.username or p.password):
            raise ValueError('Configure dedicated search JSON endpoint')
        import re
        if not re.fullmatch(r'[a-z,]{1,80}',engines):raise ValueError('Invalid configured search engines')
        self.endpoint=endpoint;self.search_host=p.hostname
        self.hosts=None if source_hosts is None else frozenset(source_hosts)
        self.deadline=float('inf');self.last_warning=None;self.sources={};self.engines=engines

    def search(self,query):
        if not isinstance(query,ApprovedQuery):raise TypeError('Only privacy-approved queries may leave the server')
        text=query.text
        audit('search',query=text,job=getattr(self,'job_id',None),policy='general-0.2')
        from research_bounds import bounded
        if self.local:raw,kind=bounded(_local_search,(text,self.engines),min(25,self.deadline-time.monotonic()))
        else:raw,kind=get(self.endpoint+'?'+urlencode({'q':text,'format':'json'}),{self.search_host},384000,seconds=self.deadline-time.monotonic())
        if kind!='application/json':raise ValueError('Search JSON unavailable')
        value=json.loads(raw);rows=value.get('results',[])
        unavailable={r[0] for r in value.get('unresponsive_engines',[]) if isinstance(r,list) and r and isinstance(r[0],str)}
        available=[e for e in self.engines.split(',') if e not in unavailable]
        if available:self.engines=','.join(available)
        if not isinstance(rows,list):raise ValueError('Invalid search results')
        terms={t for t in words(text) if len(t)>2 and t not in STOP_WORDS}
        ranked=[]
        for row in rows[:30]:
            if not isinstance(row,dict):continue
            url=row.get('url','')
            try:
                p=urlsplit(url)
                if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or not readable_url(url):continue
                if self.hosts is not None and p.hostname not in self.hosts:continue
                url=url.split('#',1)[0]
            except (ValueError,TypeError):continue
            title=str(row.get('title',''))[:200]
            description=str(row.get('content',''))[:1600]
            matches=terms & set(words(title+' '+description+' '+p.path))
            minimum=1 if len(terms)<=2 else 2
            if len(matches)<minimum:continue
            primary=any(p.hostname==h or p.hostname.endswith('.'+h) for h in ('sony.com','sonyinteractive.com','playstation.com','python.org','microsoft.com','aws.amazon.com','google.com')) or p.hostname.endswith(('.gov','.edu'))
            score=len(matches)*10+int(primary)*12
            if any(w in text.lower() for w in ('latest','current','stable')) and any(w in p.path.lower() for w in ('download','release')):score+=8
            ranked.append((score,url,{'title':title or p.hostname,'snippet':description,'published_at':row.get('publishedDate'),'query':text}))
        ranked.sort(key=lambda x:x[0],reverse=True)
        selected=[];domains={}
        for _,url,meta in ranked:
            host=urlsplit(url).hostname
            if url in selected or domains.get(host,0)>=2:continue
            domains[host]=domains.get(host,0)+1;self.sources[url]=meta;selected.append(url)
            if len(selected)==3:break
        self.last_warning='Some search engines were unavailable; source discovery may be incomplete.' if value.get('unresponsive_engines') else None
        if not selected:self.last_warning='Search returned no sufficiently relevant, readable public results. No curated fallback was substituted.'
        return selected[:2]

    def read(self,url):
        if url not in self.sources:raise ValueError('Only discovered public sources may be read')
        audit('read',url=url,job=getattr(self,'job_id',None),policy='general-0.2')
        raw,kind=get(url,self.hosts,seconds=self.deadline-time.monotonic())
        kind,_,partial=kind.partition(';')
        self.sources[url]['partial']=bool(partial)
        if kind=='text/html':
            recipe=recipe_text(raw)
            parser=Text();parser.feed(raw);raw=recipe or ' '.join(parser.main_parts or parser.parts)
            if recipe:
                self.sources[url]['recipe']=True;self.sources[url]['recipe_complete']=len(recipe)<=6000
                return raw[:6000]
        return excerpts(raw,self.sources[url].get('query',''))


def excerpts(raw,query,limit=5000):
    """Select bounded relevant passages, rather than sending a site's opening navigation."""
    import re
    text=' '.join(raw.split())
    if len(text)<=1800:return text
    terms={w for w in words(query) if len(w)>2 and w not in STOP_WORDS}
    procedural=bool(re.search(r'\b(how|steps|tutorial|connect|import|recipe|ingredients)\b',query,re.I))
    candidates=[]
    for start in range(0,len(text),550):
        chunk=text[start:start+1000];tokens=set(words(chunk))
        score=len(terms & tokens)*10
        if procedural:score+=min(12,len(tokens & {'select','choose','open','browse','navigator','load','transform','click','save','import','ingredients','mix','bake','preheat','stir','chill','oven','temperature'}))*10
        candidates.append((score,start,chunk))
    candidates.sort(key=lambda row:(-row[0],row[1]))
    selected=[]
    for score,start,chunk in candidates:
        if any(abs(start-old)<900 for old,_ in selected):continue
        selected.append((start,chunk))
        if len(selected)==4:break
    return '\n\n'.join('[Source excerpt] '+chunk for _,chunk in selected)[:limit]
