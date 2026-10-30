"""Explainable review flags; these are not calibrated correctness probabilities."""
import copy
import re

VERSION='notes-triage/1'


def annotate(page):
    if page.get('schema')=='smartinis-notes-document/1':
        result=copy.deepcopy(page);result['pages']=[annotate(p) for p in page['pages']];return result
    result=copy.deepcopy(page)
    for block in result['blocks']:
        text=block['text'];flags=list(block['uncertainties'])
        content=re.sub(r'^\s*(?:\d+[.)]|\(\d+\))\s*','',text)
        if re.search(r'\d|[€$£]',content):
            flags.append('Check numbers, amounts, dates or identifiers against the image')
        if re.search(r'\b(not|no|never|niet|geen|non|mai)\b',text,re.I):
            flags.append('Preserve negation; check that the recap does not reverse its meaning')
        if block['kind']!='heading' and re.search(
                r'[,;]\s*[A-Z][a-z]{1,}|\b[A-Z][a-z]+\s+(?:and|en|e)\s+[A-Z][a-z]+|\b[A-Z][a-z]+\s+[A-Z][a-z]+',text):
            flags.append('Possible names or technical labels: verify spelling and attribution')
        if block['kind'] in ('crossout','illegible'):
            flags.append('Excluded source: confirm crossed-out or unreadable material is not promoted')
        block['uncertainties']=list(dict.fromkeys(flags))
    return result
