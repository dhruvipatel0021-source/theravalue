import requests
import xml.etree.ElementTree as ET

BASE='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
SCOPE='(type 2 diabetes) AND (semaglutide OR tirzepatide OR dulaglutide OR liraglutide)'

def search_pubmed(question, limit=15):
    r=requests.get(BASE+'esearch.fcgi',params={'db':'pubmed','term':f'({question}) AND {SCOPE}','retmode':'json','retmax':limit,'sort':'relevance'},timeout=25); r.raise_for_status()
    ids=r.json()['esearchresult']['idlist']
    if not ids:return []
    r=requests.get(BASE+'efetch.fcgi',params={'db':'pubmed','id':','.join(ids),'retmode':'xml'},timeout=30);r.raise_for_status()
    out=[]
    for a in ET.fromstring(r.content).findall('.//PubmedArticle'):
        pmid=a.findtext('.//PMID'); title=a.find('.//ArticleTitle'); abstract=a.findall('.//Abstract/AbstractText')
        out.append({'PMID':pmid,'Title':''.join(title.itertext()) if title is not None else '', 'Abstract':'\n'.join(''.join(t.itertext()) for t in abstract),'URL':f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/'})
    return out

def incremental(a,b,days_a,days_b,weeks,effect):
    if min(a,b)<0 or min(days_a,days_b,weeks)<=0 or effect<=0:raise ValueError('Invalid model inputs')
    ca=a*weeks*7/days_a; cb=b*weeks*7/days_b; delta=ca-cb
    return {'Intervention cost':ca,'Comparator cost':cb,'Incremental cost':delta,'Additional HbA1c reduction (pp)':effect,'Cost per additional pp':delta/effect}
