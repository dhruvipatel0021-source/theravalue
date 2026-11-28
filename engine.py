import time, requests, xml.etree.ElementTree as ET, math
def get(url, **kwargs):
    for i in range(3):
        try:
            r=requests.get(url, **kwargs)
            if r.status_code not in (429,500,502,503,504): return r
        except requests.RequestException:
            if i==2: raise
        time.sleep(1.5*(i+1))
    return r

BASE='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
def search_pubmed(query,limit=30):
    r=get(BASE+'esearch.fcgi',params={'db':'pubmed','term':query,'retmode':'json','retmax':limit,'sort':'relevance','tool':'theravalue' },timeout=30);r.raise_for_status(); ids=r.json()['esearchresult']['idlist']
    if not ids:return []
    time.sleep(.4)
    r=get(BASE+'efetch.fcgi',params={'db':'pubmed','id':','.join(ids),'retmode':'xml'},timeout=30);r.raise_for_status();out=[]
    for a in ET.fromstring(r.content).findall('.//PubmedArticle'):
        pmid=a.findtext('.//PMID'); title=a.find('.//ArticleTitle'); types=[t.text for t in a.findall('.//PublicationType')]; abstract='\n'.join(''.join(t.itertext()) for t in a.findall('.//Abstract/AbstractText'))
        out.append(dict(PMID=pmid,Title=''.join(title.itertext()) if title is not None else '',Abstract=abstract,Design='; '.join(types),URL=f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/'))
    return out

def full_text(pmid):
    r=requests.get('https://www.ebi.ac.uk/europepmc/webservices/rest/search',params={'query':f'EXT_ID:{pmid} AND SRC:MED','format':'json','resultType':'core'},timeout=25);r.raise_for_status(); records=r.json()['resultList']['result']; pmc=next((x.get('pmcid') for x in records if x.get('pmcid')),None)
    if not pmc:return None
    r=requests.get(f'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmc}/fullTextXML',timeout=30)
    if r.status_code==404:return None
    r.raise_for_status(); root=ET.fromstring(r.content); body=root.find('.//body'); return ('\n'.join(' '.join(''.join(x.itertext()).split()) for x in body.findall('.//p')) if body is not None else '',f'https://europepmc.org/articles/{pmc}')

def incremental(a,b,days_a,days_b,weeks,effect):
    if not all(math.isfinite(x) for x in (a,b,days_a,days_b,weeks,effect)) or min(a,b)<0 or min(days_a,days_b,weeks)<=0:raise ValueError('Invalid inputs')
    ca=a*weeks*7/days_a;cb=b*weeks*7/days_b;delta=ca-cb
    return {'Intervention cost':ca,'Comparator cost':cb,'Incremental cost':delta,'Additional HbA1c reduction (pp)':effect,'Cost per additional pp':delta/effect if effect>0 and delta>=0 else None}

def compatible(a,b):
    fields=['PMID','outcome','unit','measure','weeks','population','estimand']
    return all(a.get(k) not in (None,'','unknown') and a.get(k)==b.get(k) for k in fields) and a.get('arm')!=b.get('arm') and a.get('measure')=='change from baseline' and a.get('design')==b.get('design')=='direct randomized trial'


def passage_status(quote,source):
    import re, unicodedata
    def norm(x):return ' '.join(unicodedata.normalize('NFKC',x).split())
    if not isinstance(quote,str) or not quote.strip() or not source:return 'Source not located'
    q=norm(quote);src=norm(source)
    if q in src:return 'Exact source match'
    pieces=[x.strip() for x in re.split(r'\.{3,}|…',q) if x.strip()]
    if len(pieces)>1 and sum(map(len,pieces))>=25:
        pos=0
        for piece in pieces:
            idx=src.find(piece,pos)
            if idx<0:return 'Source not located'
            pos=idx+len(piece)
        return 'Partial source match'
    return 'Source not located'

def evidence_check(r):
    import re
    q=r.get('quote') or ''; source=r.get('source_text') or ''
    status=passage_status(q,source)
    if status!='Exact source match':return status
    nums=[float(x.replace('−','-')) for x in re.findall(r'[-−+]?\d+(?:\.\d+)?',q)]
    v=r['value']
    if r.get('value_origin')=='calculated':
        a,b=r.get('baseline'),r.get('followup')
        if isinstance(a,(int,float)) and isinstance(b,(int,float)) and a in nums and b in nums and abs(b-a-v)<1e-7:return 'Arithmetic consistent'
        return 'Calculation needs review'
    return 'Number located' if v in nums else 'Number needs review'

def comparison(a,b):
    fields=['PMID','outcome','unit','measure','weeks','population','comparison_group']
    return all(a.get(k) not in (None,'','unknown') and a.get(k)==b.get(k) for k in fields) and a.get('arm')!=b.get('arm') and a.get('design')==b.get('design')=='direct randomized trial'

def budget_model(n,a,b,da,db,uptake,years):
    if min(n,da,db,years)<=0 or min(a,b)<0 or not 0<=uptake<=100:raise ValueError('Invalid scenario')
    old=n*a/da*365*years; delta=n*uptake/100*(b/db-a/da)*365*years
    return {'Current expenditure':old,'Scenario expenditure':old+delta,'Change':delta,'Switching patients':n*uptake/100}
