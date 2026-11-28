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

ALIASES={'tirzepatide':['tirzepatide','mounjaro','zepbound'],'semaglutide':['semaglutide','ozempic','rybelsus','wegovy'],'liraglutide':['liraglutide','victoza','saxenda'],'dulaglutide':['dulaglutide','trulicity'],'exenatide':['exenatide','byetta','bydureon'],'lixisenatide':['lixisenatide','adlyxin']}
def drugs_in(text):
    import re
    return [d for d,aliases in ALIASES.items() if any(re.search(r'\b'+a+r'\b',text.lower()) for a in aliases)]
def build_query(q):
    import re
    if re.fullmatch(r'\d+(?:\[PMID\])?',q.strip(),re.I):return q.split('[')[0].strip()+'[PMID]'
    if '[' in q:return q
    drugs=drugs_in(q)
    if not drugs:raise ValueError('Name at least one GLP-1 therapy or enter a PubMed query.')
    return ' AND '.join(['('+' OR '.join(a+'[tiab]' for a in ALIASES[d])+')' for d in drugs]+['("Diabetes Mellitus, Type 2"[MeSH Terms] OR "type 2 diabetes"[tiab] OR T2DM[tiab])'])
def screen(p,q):
    text=p['Title']+' '+p['Abstract']; t=text.lower(); design=p['Design'].lower(); drugs=drugs_in(q)
    if '[pmid]' in q.lower() or q.strip().isdigit():return 'Uncertain','Requested publication; confirm eligibility.'
    if not any(x in t for x in ['type 2 diabetes','type 2 diabetic','t2dm','type ii diabetes']):return 'Uncertain','Type 2 diabetes population not established in retrieved text.'
    if not all(d in drugs_in(text) for d in drugs):return 'Supporting','Not all requested therapies identified.'
    if any(x in t for x in ['network meta-analysis','systematic review','meta-analysis']) or 'review' in design:return 'Supporting','Evidence synthesis; may include indirect comparisons.'
    if 'randomized controlled trial' in design or 'randomised controlled trial' in design or ('random' in t and 'trial' in t):return 'Uncertain','Potential head-to-head trial; confirm randomized arms and population.'
    return 'Supporting','Other potentially relevant evidence; confirm design and outcomes.'
def recover_passage(row,source):
    import re,unicodedata
    def norm(s):return unicodedata.normalize('NFKC',s).replace('−','-').replace('–','-')
    v=row['value']; quote=row.get('quote') or ''
    if passage_status(quote,source)=='Exact source match':return quote
    # Candidate passages are not automatically verified. Require numerical match and rank by arm/outcome terms.
    chunks=re.split(r'(?<=[.!?])\s+|\n+',source)
    tokens=set(re.findall(r'[a-z]{4,}',(row.get('arm') or '').lower()+' '+(row.get('outcome') or '').lower()))
    candidates=[]
    for c in chunks:
        nums=[float(x) for x in re.findall(r'[-+]?\d+(?:\.\d+)?',norm(c))]
        if v in nums:
            score=sum(t in c.lower() for t in tokens)
            if score:candidates.append((score,c))
    return max(candidates,key=lambda x:x[0])[1] if candidates else quote

def direct_contrast(r):
    return r.get('design')=='direct randomized trial' and r.get('measure')=='between-arm difference' and bool(r.get('comparator')) and bool(r.get('arm')) and r.get('weeks') and r.get('outcome') in ('HbA1c','weight') and r.get('unit') in ('pp','kg')

# Normalize typography, not scientific meaning.
def normalize_source(s):
    import re, unicodedata
    s=unicodedata.normalize('NFKC',str(s)).replace('−','-').replace('–','-')
    return re.sub(r'(?<=\d)[·∙](?=\d)', '.', s)

def screen(p,q):
    import re
    t=normalize_source(p['Title']+' '+p['Abstract']).lower(); title=p['Title'].lower(); drugs=drugs_in(q)
    if not drugs:return 'Uncertain','Confirm eligibility for requested publication.'
    if not all(d in drugs_in(t) for d in drugs):return 'Supporting','Not all requested therapies identified.'
    if not re.search(r'type[ -]?(?:2|ii) diabet|\bt2dm\b',t):return 'Uncertain','Population not established.'
    if re.search(r'meta.analysis|systematic review',title):return 'Supporting','Evidence synthesis; inspect direct and indirect estimates.'
    randomized='randomized controlled trial' in p['Design'].lower() or bool(re.search(r'randomi[sz]',t))
    if len(drugs)>=2 and randomized and all(d in drugs_in(title) for d in drugs) and re.search(r'\bversus\b|\bvs\.?\b|\bcompar',title):
        return 'Direct','Candidate randomized head-to-head study; confirm requested outcomes and arms.'
    return 'Uncertain','Confirm study design, treatment arms and requested outcomes.'

def evidence_check(r):
    import re
    q=r.get('quote') or ''; src=r.get('source_text') or ''
    if passage_status(q,src)!='Exact source match':return 'Source not located'
    q=normalize_source(q).lower(); arm=normalize_source(r.get('arm') or '').lower()
    drugs=drugs_in(arm)
    if not drugs or not all(d in drugs_in(q) for d in drugs):return 'Arm needs review'
    doses=re.findall(r'\b\d+(?:\.\d+)?\s*mg\b',arm)
    if any(not re.search(r'(?<![\d.])'+re.escape(d.replace(' ',''))+r'(?!\w)',q.replace(' ','')) for d in doses):return 'Dose needs review'
    outcome=str(r.get('outcome') or '').lower()
    patterns={'hba1c':r'hba\s*1c|glycat\w* h[ae]emoglobin|glycated hemoglobin','weight':r'weight','nausea':r'nausea','vomiting':r'vomit','diarrhea':r'diarrh','discontinuation':r'discontinu','gastrointestinal adverse events':r'gastrointestinal'}
    if not re.search(patterns.get(outcome,re.escape(outcome) if outcome else r'(?!)'),q):return 'Outcome needs review'
    nums=[float(x) for x in re.findall(r'[-+]?\d+(?:\.\d+)?',q)]
    v=r['value']; signed=v in nums or (v<0 and -v in nums and bool(re.search(r'reduc|decreas|loss|lower',q)))
    if not signed:return 'Number needs review'
    if r.get('measure')=='between-arm difference' and (not r.get('comparator') or not all(d in drugs_in(q) for d in drugs_in(r['comparator']))):return 'Comparator needs review'
    return 'Number located' # candidate only; individual human semantic review required
