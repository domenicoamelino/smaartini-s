"""Local declassification checks. No topic catalog, no model-only egress approval."""
from dataclasses import dataclass
import html
import base64
import re
import unicodedata
from urllib.parse import unquote


class PrivacyBlocked(ValueError):
    """A proposed public brief/query cannot safely leave the local boundary."""


class QueryReviewRequired(ValueError):
    def __init__(self,queries,reason):
        self.queries=list(queries);self.reason=reason;self.checkpoint=None
        super().__init__('User review required for exact public queries')


def normalized(text):
    text=unicodedata.normalize('NFKC',str(text))
    for _ in range(3):text=unquote(html.unescape(text))
    text=text.casefold().translate(str.maketrans('аеорсухіјкмтнвαεορτχ','aeopcyxijkmthbaEoptx'.lower()))
    return ' '.join(text.split())


def words(text):return re.findall(r'[^\W_]+',normalized(text),re.UNICODE)


PUBLIC_ACRONYMS=frozenset('API HTTP HTTPS SQL REST JSON XML HTML CPU GPU RAM DNS TLS SSL TCP UDP RFC SDK UI UX SRE RAG AI LLM ETL ERP SAP HANA S4HANA ABAP BTP SAC IBP EPM CPM CRM SCM BPC SSO OAUTH ODATA BI CSV XLSX XLS XLSM PDF URL GET POST PUT DELETE AWS GCP GDPR ISO'.split())
PUBLIC_TECH_NAMES=frozenset('PlayStation OpenAI OpenWebUI GitHub GitLab PostgreSQL MySQL JavaScript TypeScript PowerBI'.split())|{'Microsoft Excel','Microsoft Power','Power Query','Power BI','SAP Analytics Cloud'}
PUBLIC_TECH_WORDS=frozenset('PYTHON JAVA JAVASCRIPT TYPESCRIPT CSHARP CPP RUST GO GOLANG RUBY PHP SWIFT KOTLIN SCALA JULIA MATLAB SQLITE POSTGRES POSTGRESQL MYSQL MARIADB REDIS KAFKA DOCKER PODMAN KUBERNETES LINUX WINDOWS UBUNTU DEBIAN ANDROID IOS MACOS EXCEL POWERBI TABLEAU DAX AZURE MICROSOFT GOOGLE SONY PLAYSTATION'.split())
COMMON_WORDS=frozenset('A AN THE AND OR BUT IF IN ON AT TO OF FOR FROM WITH WITHOUT AS BY IS ARE WAS WERE BE BEEN BEING IT ITS THIS THAT THESE THOSE I WE YOU HE SHE THEY MY OUR YOUR THEIR NOT NO YES SO DO DOES DID HAS HAVE HAD CAN COULD SHOULD WOULD WILL MAY MIGHT MUST ALL ANY SOME EACH OTHER MORE MOST LESS ONLY ALSO ABOUT INTO OVER UNDER AFTER BEFORE DURING BETWEEN THROUGH WHERE WHEN WHY HOW WHAT WHICH WHO US UK EU JANUARY FEBRUARY MARCH APRIL MAY JUNE JULY AUGUST SEPTEMBER OCTOBER NOVEMBER DECEMBER MONDAY TUESDAY WEDNESDAY THURSDAY FRIDAY SATURDAY SUNDAY PUBLIC PRIVATE INTERNAL EXTERNAL SOURCE SOURCES TITLE DATE TIME STATUS SUMMARY NOTES NOTE ACTION ACTIONS DECISION DECISIONS PARTICIPANTS TEXT AUDIO DRAFT APPROVED KNOWLEDGE DATA RAW READ WRITE VERSION ID NULL NONE TRUE FALSE UPDATE CURRENT LATEST NEW OLD TECHNICAL RISK RISKS'.split())
COMMON_WORDS=COMMON_WORDS|frozenset('ARCHITECTURE INTEGRATION INTEGRATED MIGRATION VALIDATION TEST TESTING DEPLOYMENT RELIABILITY PLANNING BUSINESS SYNCHRONIZATION SYSTEM SYSTEMS ANALYTICS ENVIRONMENT PROCESS PROCESSES PROJECT TEAM BASE CONTENT MAINTENANCE MANAGEMENT INFORMATION DATABASE WORKFLOW WORKFLOWS AUTOMATION CHANGE CONTROL CONTRACT INTERFACE INTERFACES QUALITY PERFORMANCE SOFTWARE ENGINEERING DEVELOPMENT SERVICES SERVICE APPLICATION APPLICATIONS STORAGE NETWORK INFRASTRUCTURE SECURITY ACCESS AUTHENTICATION AUTHORIZATION REQUIREMENTS SOLUTION SOLUTIONS DESKTOP WORKBOOK WORKBOOKS QUERY CONNECTOR FILE IMPORT EXPORT PRACTICES PRACTICE STRATEGY STRATEGIES CLOUD GATEWAY LAYER MULTI CORE ROUTING'.split())
PRIVATE_LANGUAGE=re.compile(r'\b(my|our)\s+(?:(?:latest|recent|private|internal)\s+)*(meetings?|discussions?|notes?|documents?|recaps?|transcripts?|team|company)\b|\b(?:confidential|private|internal)\s+(?:meeting|notes|document|transcript|project|company|customer|client|discussion)\b',re.I)
SECRET=re.compile(r'\b(?:sk-[\w-]{8,}|bearer\s+\S+|(?:password|api[_ -]?key|access[_ -]?token)\s*[:=]\s*\S+)|[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b(?:\d{1,3}\.){3}\d{1,3}\b|\b[a-f0-9]{20,}\b',re.I)


def contains(text,phrase):
    phrase=normalized(phrase)
    return bool(phrase and re.search(r'(?<!\w)'+re.escape(phrase)+r'(?!\w)',text))


def private_intent(question,identifiers=()):
    text=normalized(question)
    return bool(PRIVATE_LANGUAGE.search(text) or any(contains(text,name) for name in identifiers))


def identifiers_from_private(text):
    values={word for word in re.findall(r'\b[A-Z][A-Z0-9_-]{1,30}\b',text) if word not in PUBLIC_ACRONYMS and word not in COMMON_WORDS}
    for value in re.findall(r'\b[A-Z][a-z\u00c0-\u024f]+(?:\s+[A-Z][a-z\u00c0-\u024f]+){1,3}\b',text):
        if not all(w.upper() in COMMON_WORDS for w in value.split()):values.add(value)
    for value in re.findall(r'\b[A-Z][a-z]+(?:[A-Z][A-Za-z0-9]+)+\b',text):
        values.add(value)
    # Explicit project/codename labels are authoritative even for ordinary words.
    values.update(re.findall(r'\b(?i:project|codename|initiative)\s*[:=-]?\s+([A-Z][A-Za-z0-9_-]+)',text))
    return {value for value in values if value not in PUBLIC_TECH_NAMES and value.upper() not in PUBLIC_TECH_WORDS}


@dataclass(frozen=True)
class ApprovedQuery:
    text: str


class Guard:
    def __init__(self,question,private=(),identifiers=(),sensitive=False):
        self.identifiers={normalized(x) for x in identifiers if str(x).strip()}
        self.private_texts=[s['text'] if isinstance(s,dict) else str(s) for s in private]
        self.sensitive=sensitive or private_intent(question,self.identifiers)
        if self.sensitive:self.private_texts.append(question)
        for value in self.private_texts:self.identifiers.update(normalized(x) for x in identifiers_from_private(value))
        self.quotes=[];self.ngrams=set()
        for value in self.private_texts:
            for quote in re.findall(r'["“”]([^"“”\n]{5,})["“”]',value):self.quotes.append(normalized(quote))
            tokens=words(value)
            self.ngrams.update(tuple(tokens[i:i+6]) for i in range(max(0,len(tokens)-5)))

    def check(self,text,allow_identifiers=False):
        if not isinstance(text,str) or not 2<=len(text)<=600:raise PrivacyBlocked('Invalid public wording')
        norm=normalized(text)
        if (SECRET.search(norm) or PRIVATE_LANGUAGE.search(norm) or
                re.search(r'https?://|www\.|[<>@\\]|["“”]|\b[a-z0-9+/=_-]{28,}\b',norm) or
                any(unicodedata.category(c).startswith('C') for c in text)):
            raise PrivacyBlocked('Sensitive or encoded public wording')
        matched=[name for name in self.identifiers if contains(norm,name)]
        raw=' '.join(text.casefold().split())
        if any(not re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',raw) for name in matched):
            raise PrivacyBlocked('Encoded private identifier')
        if not allow_identifiers and matched:raise PrivacyBlocked('Private identifier in public wording')
        if re.search(r'\b(?:[a-z]\s+){2,}[a-z]\b',norm):raise PrivacyBlocked('Spelled-out encoded wording')
        for token in re.findall(r'\b[A-Za-z0-9+/=_-]{4,128}\b',text):
            decoded=[]
            try:decoded.append(base64.b64decode(token+'='*((-len(token))%4),validate=True).decode('utf-8'))
            except (ValueError,UnicodeError):pass
            try:decoded.append(bytes.fromhex(token).decode('utf-8'))
            except (ValueError,UnicodeError):pass
            if any(any(contains(normalized(value),name) for name in self.identifiers) or SECRET.search(value) for value in decoded):
                raise PrivacyBlocked('Encoded private identifier')
        if any(quote in norm for quote in self.quotes):raise PrivacyBlocked('Private quote in public wording')
        tokens=words(norm)
        if any(tuple(tokens[i:i+6]) in self.ngrams for i in range(max(0,len(tokens)-5))):raise PrivacyBlocked('Private passage in public wording')
        return ' '.join(text.split())

    def approve(self,queries,verdict,user_approved=False):
        # Hard disclosure checks remain enforced even after a human marks names public.
        for q in queries:self.check(q,allow_identifiers=True)
        if user_approved:return [ApprovedQuery(self.check(q,allow_identifiers=True)) for q in queries]
        if (not isinstance(verdict,dict) or set(verdict)!={'decision'} or verdict['decision']!='safe'):
            raise QueryReviewRequired(queries,'The local review could not establish that all wording is public.')
        if any(any(contains(normalized(q),name) for name in self.identifiers) for q in queries):
            raise QueryReviewRequired(queries,'A proposed query contains a name or term also present in private material.')
        return [ApprovedQuery(self.check(q)) for q in queries]


def route(value):
    if (not isinstance(value,dict) or set(value)!={'knowledge','web'} or any(type(value[k]) is not bool for k in value)):
        raise ValueError('Invalid research routing')
    return value


def plan(value):
    if not isinstance(value,dict) or set(value)!={'queries'}:raise ValueError('Invalid research plan')
    queries=value['queries']
    if (not isinstance(queries,list) or not 1<=len(queries)<=3 or any(not isinstance(q,str) or not 2<=len(q)<=240 for q in queries)):
        raise ValueError('Invalid public queries')
    return list(dict.fromkeys(' '.join(q.split()) for q in queries))
