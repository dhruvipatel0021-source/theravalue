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
