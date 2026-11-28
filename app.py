import streamlit as st
import pandas as pd
import plotly.express as px
import json
from engine import search_pubmed, incremental, full_text, compatible
from ai import plan, numeric_extract, ask
st.set_page_config(page_title='TheraValue | Research workspace',layout='wide',page_icon='📊')
st.markdown("""<style>
.stApp {background:#f4f7fa;color:#132f43} .block-container{max-width:1250px;padding-top:2.4rem;padding-bottom:3rem} [data-testid="stSidebar"]{background:#e8eff4} h1,h2,h3{color:#132f43;letter-spacing:-.035em} h1{font-size:2rem} h2{font-size:1.4rem} h3{font-size:1.15rem} [data-testid="stMetric"], [data-testid="stVerticalBlockBorderWrapper"]{background:white;border-radius:14px} .hero{background:linear-gradient(115deg,#132f43,#235e69);color:white;padding:30px;border-radius:18px;margin-bottom:22px} .hero h1{color:white;margin:0;font-size:2.1rem} .hero p{color:#d4e7ed;margin:8px 0 0} .eyebrow{font-size:11px;letter-spacing:2px;font-weight:700;color:#287f77} .hero .eyebrow{color:#9bd9ce} .stButton button[kind="primary"]{background:#287f77;border-color:#287f77;color:white} [data-testid="stSidebar"] button{width:100%;text-align:left;justify-content:flex-start;border-radius:9px} </style>""",unsafe_allow_html=True)
PAGES=['Overview','HEOR & Formulary','Clinical Review','Evidence Library','My Assessments','Methodology']
for k,v in {'page':'Overview','reports':[],'papers':[],'extractions':{},'search_terms':'','plan':None}.items():
    if k not in st.session_state:st.session_state[k]=v
try: KEY=st.secrets.get('GROQ_API_KEY','')
except Exception: KEY=''
def go(p):st.session_state.page=p
st.sidebar.markdown('### TheraValue\n\nEvidence & value intelligence')
st.sidebar.caption('WORKSPACE')
for i,p in enumerate(PAGES):
    if i==3: st.sidebar.caption('RESOURCES')
    st.sidebar.button(p,key='nav'+str(i),on_click=go,args=(p,),type='primary' if st.session_state.page==p else 'secondary',use_container_width=True)
st.sidebar.divider();st.sidebar.caption('Research edition · Type 2 diabetes');st.sidebar.caption('AI key configured' if KEY else 'AI key not configured');st.sidebar.caption('Research only. No identifiable patient information.')
page=st.session_state.page

for k,v in {'rows':[],'notes':{},'queries':[]}.items():
    if k not in st.session_state:st.session_state[k]=v

def evidence():
    st.subheader('Find evidence');q=st.text_area('Research question or PubMed query',placeholder='Compare tirzepatide and semaglutide in adults with type 2 diabetes',key='question')
    direct=st.checkbox('Prioritize randomized trials',value=True)
    if st.button('Retrieve studies',type='primary',disabled=not q.strip()):
        try:
            with st.spinner('Searching PubMed…'):
                if '[PMID]' in q or '[tiab]' in q: terms=q
                else:
                    try: terms=ask(KEY,'Return JSON with query: a sensitive PubMed Boolean search using drug names and population only. Do not require outcomes, dates or study design. No extra fields.',q)['query']
                    except Exception: terms=q
                queries=[terms+' AND randomized controlled trial[pt]',terms] if direct and '[PMID]' not in terms else [terms]
                found={}
                for query in queries:
                    for p in search_pubmed(query):found.setdefault(p['PMID'],p)
                st.session_state.papers=list(found.values());st.session_state.queries=queries
        except Exception:st.error('Retrieval failed. Retry or use a direct PMID.')
    if st.session_state.queries:
        with st.expander('Search audit'):st.write(st.session_state.queries)
    papers=st.session_state.papers
    st.caption(f'{len(papers)} retrieved records (limited search, not exhaustive). Publication types are preliminary screening metadata.')
    selected=st.multiselect('Select studies for extraction (up to 3 per batch)',[p['PMID'] for p in papers],format_func=lambda id:next(p['Title'] for p in papers if p['PMID']==id),max_selections=3)
    use_full=st.checkbox('Try available Europe PMC full text',value=True)
    if st.button('Extract numerical evidence',disabled=not selected or not KEY):
        for p in papers:
            if p['PMID'] not in selected:continue
            try:
                with st.spinner('Extracting '+p['PMID']):
                    source=p['Abstract'];url=p['URL'];label='Abstract'
                    if use_full:
                        try:
                            ft=full_text(p['PMID'])
                            if ft and ft[0]:source=ft[0][:36000];url=ft[1];label='Full-text paragraphs (first 36,000 characters; tables excluded)'
                        except Exception:st.warning('Full text unavailable; using abstract.')
                    if not source:st.warning('No accessible source text.');continue
                    rows,notes=numeric_extract(KEY,p,source,url)
                    for r in rows:r['source_scope']=label
                    st.session_state.rows=[r for r in st.session_state.rows if r['PMID']!=p['PMID']]+rows;st.session_state.notes[p['PMID']]=notes
            except Exception:st.error('Extraction failed for '+p['PMID']+'; retry or check rate limits.')
    for p in papers:
        with st.expander(p['Title']):
            st.caption(p['Design']);st.write(p['Abstract']);st.markdown(f"[PubMed source]({p['URL']})")

def review():
    st.subheader('Extracted evidence & verification')
    if not st.session_state.rows:st.info('Retrieve and extract studies first.');return
    df=pd.DataFrame(st.session_state.rows);st.caption('Exact passage matching does not establish correct interpretation. Review each row against the original source before approval.')
    edited=st.data_editor(df,disabled=[c for c in df.columns if c!='reviewed'],hide_index=True,key='review_table',use_container_width=True)
    if st.button('Apply review decisions'):
        st.session_state.rows=edited.to_dict('records');st.success('Review decisions saved for this session.')
    st.download_button('Export evidence CSV',df.to_csv(index=False),'theravalue_evidence.csv','text/csv')
    with st.expander('Extraction limitations'):st.write(st.session_state.notes)
    for (pmid,outcome,unit,measure,weeks),group in df.dropna(subset=['weeks','unit','measure','outcome']).groupby(['PMID','outcome','unit','measure','weeks']):
        if len(group)>1:
            st.caption(f'{pmid} · {outcome} · {measure} · {weeks} weeks · draft evidence')
            st.plotly_chart(px.bar(group,x='arm',y='value',color_discrete_sequence=['#287f77'],labels={'value':unit}),use_container_width=True)

def economics():
    st.subheader('Trial-matched medication cost analysis')
    rows=[r for r in st.session_state.rows if r['reviewed'] and r['passage_match'] and r['outcome']=='HbA1c' and r['unit']=='pp']
    pairs=[(a,b) for a in rows for b in rows if compatible(a,b)]
    if not pairs:st.info('Requires two reviewed, passage-matched HbA1c change rows from the same direct randomized trial, with matching known population, estimand and follow-up. No cross-trial pooling.');return
    a,b=st.selectbox('Select comparison',pairs,format_func=lambda p:f"{p[0]['arm']} vs {p[1]['arm']} · PMID {p[0]['PMID']}")
    perspective=st.selectbox('Cost basis',['Patient out-of-pocket','Cash price','Payer net cost','Acquisition benchmark'])
    ca=st.number_input('Intervention supply cost ($)',min_value=0.,value=None);da=st.number_input('Intervention supply days',min_value=1,value=None);sa=st.text_input('Intervention cost source and date')
    cb=st.number_input('Comparator supply cost ($)',min_value=0.,value=None);db=st.number_input('Comparator supply days',min_value=1,value=None);sb=st.text_input('Comparator cost source and date')
    confirmed=st.checkbox('Confirm same cost basis, currency year and dose-specific costs; values are signed changes from baseline.')
    if None not in (ca,cb,da,db) and sa.strip() and sb.strip() and confirmed:
        effect=b['value']-a['value'];r=incremental(ca,cb,da,db,a['weeks'],effect);st.json(r)
        st.caption('Medication expenditure only; constant prices and continuous therapy assumed. Not a QALY-based cost-effectiveness analysis. Differences are calculated from extracted arm means, not adjusted treatment contrasts.')
        sens=[]
        for m in [.8,1,1.2]:sens.append({'Intervention price multiplier':m,**incremental(ca*m,cb,da,db,a['weeks'],effect)})
        st.plotly_chart(px.line(pd.DataFrame(sens),x='Intervention price multiplier',y='Incremental cost',markers=True),use_container_width=True)
        if st.button('Save assessment'):st.session_state.reports.append({'type':'Trial-matched cost analysis','evidence':[a,b],'perspective':perspective,'inputs':[ca,da,sa,cb,db,sb],'results':r,'sensitivity':sens})

if page=='Overview':
    st.markdown('<div class="hero"><div class="eyebrow">RESEARCH EDITION / TYPE 2 DIABETES</div><h1>Evidence &amp; value intelligence</h1><p>From published evidence to transparent clinical and economic assessment.</p></div>',unsafe_allow_html=True)
    for col,p,desc in zip(st.columns(2),PAGES[1:3],['Retrieve, verify and compare clinical evidence; model medication expenditure.','Identify clinical information gaps and supporting evidence.']):
        with col:
            with st.container(border=True):st.subheader(p);st.write(desc);st.button('Open '+p,on_click=go,args=(p,),type='primary')
    st.subheader('Current session');a,b,c=st.columns(3);a.metric('Retrieved studies',len(st.session_state.papers));b.metric('Extracted rows',len(st.session_state.rows));c.metric('Reviewed rows',sum(bool(r['reviewed']) for r in st.session_state.rows))
    st.caption('Research prototype · no manual reference workbook embedded.')
elif page=='HEOR & Formulary':
    st.title('HEOR & Formulary');t1,t2,t3=st.tabs(['1 · Retrieve','2 · Verify','3 · Analyze'])
    with t1:evidence()
    with t2:review()
    with t3:economics()
elif page=='Clinical Review':
    st.title('Clinical decision review');st.caption('Research-only information-gap assessment; not validated prescribing support. No patient identifiers.')
    case=st.text_area('Describe a hypothetical clinical scenario');details=st.text_area('Known clinical factors: goals, current treatment, comorbidities, prior intolerance, affordability')
    if st.button('Identify evidence needs',disabled=not case.strip() or not KEY):
        try:
            r=ask(KEY,'Return JSON with missing_information (array), clinical_questions (array), safety_topics_to_verify (array), affordability_questions (array). Identify information gaps only; no drug recommendations, safety determinations or invented citations.',case+'\n'+details);st.session_state.clinical=r
        except Exception:st.error('AI unavailable. Retry later.')
    if 'clinical' in st.session_state:st.json(st.session_state.clinical)
    st.button('Open evidence retrieval',on_click=go,args=('HEOR & Formulary',))
elif page=='Evidence Library':
    st.title('Evidence library');review()
elif page=='My Assessments':
    st.title('My assessments');st.caption('Session only; export before leaving.')
    for i,r in enumerate(st.session_state.reports):
        with st.expander(f'Assessment {i+1}'):st.json(r);st.download_button('Export JSON',json.dumps(r,indent=2,default=str),f'assessment_{i+1}.json',key=f'dl{i}')
else:
    st.title('Methodology');st.write('Independent PubMed retrieval; optional accessible Europe PMC text; Groq numerical extraction; human review; conservative same-trial compatibility checks; deterministic medication expenditure.');st.warning('Pilot only. Full-text tables, economic literature extraction, insurance, clinical safety rules, persistent storage and formal validation are not implemented. Manual reference data remains separate.')
