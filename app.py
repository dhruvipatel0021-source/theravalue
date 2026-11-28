import streamlit as st
import pandas as pd
import plotly.express as px
import json, re, itertools
from datetime import datetime
from engine import search_pubmed, incremental, full_text, compatible
from ai import plan, numeric_extract, ask
st.set_page_config(page_title='TheraValue | Research workspace',layout='wide',page_icon='📊')
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Inter:wght@400;500;600&display=swap'); html, body, [data-testid="stAppViewContainer"] {font-family:Inter, sans-serif} h1,h2,h3 {font-family:Manrope,sans-serif!important}
.stApp {background:#f4f7fa;color:#132f43} .block-container{max-width:1250px;padding-top:2.4rem;padding-bottom:3rem} [data-testid="stSidebar"]{background:#e8eff4} h1,h2,h3{color:#132f43;letter-spacing:-.035em} h1{font-size:2.65rem} h2{font-size:1.75rem} h3{font-size:1.15rem} [data-testid="stMetric"], [data-testid="stVerticalBlockBorderWrapper"]{background:white;border-radius:14px} .hero{background:linear-gradient(115deg,#132f43,#235e69);color:white;padding:30px;border-radius:18px;margin-bottom:22px} .hero h1{color:white;margin:0;font-size:2.1rem} .hero p{color:#d4e7ed;margin:8px 0 0} .eyebrow{font-size:11px;letter-spacing:2px;font-weight:700;color:#287f77} .hero .eyebrow{color:#9bd9ce} .stButton button[kind="primary"]{background:#287f77;border-color:#287f77;color:white} [data-testid="stSidebar"] button{width:100%;text-align:left;justify-content:flex-start;border-radius:9px} </style>""",unsafe_allow_html=True)
PAGES=['Overview','HEOR & Formulary','Clinical Review','Evidence Library','My Assessments','Methodology']
for k,v in {'page':'Overview','reports':[],'papers':[],'extractions':{},'search_terms':'','plan':None}.items():
    if k not in st.session_state:st.session_state[k]=v
try: KEY=st.secrets.get('GROQ_API_KEY','')
except Exception: KEY=''
def go(p):st.session_state.page=p
st.sidebar.markdown('### TheraValue\n\nClinical & pharmacoeconomic research')
st.sidebar.caption('WORKSPACE')
for i,p in enumerate(PAGES):
    if i==3: st.sidebar.caption('RESOURCES')
    st.sidebar.button(p,key='nav'+str(i),on_click=go,args=(p,),type='primary' if st.session_state.page==p else 'secondary',use_container_width=True)
st.sidebar.divider();st.sidebar.caption('Research edition · Type 2 diabetes');st.sidebar.caption('AI key configured' if KEY else 'AI key not configured');st.sidebar.caption('Research only. No identifiable patient information.')
page=st.session_state.page

for k,v in {'rows':[],'notes':{},'queries':[],'stage':0,'objective':0}.items():
    if k not in st.session_state:st.session_state[k]=v

OBJECTIVES=[('Compare therapies','Drug A vs Drug B: efficacy, safety and tolerability'),('Evaluate economic value','Additional medication cost per unit of clinical benefit'),('Estimate budget impact','Annual expenditure after a change in formulary uptake'),('Conduct a formulary review','Clinical evidence, published economics and access considerations')]
EXAMPLES=["How does Drug A compare with Drug B for HbA1c reduction and adverse effects?","What is the additional medication cost of Drug A versus Drug B per additional HbA1c reduction?","What is the annual pharmacy expenditure impact of switching 20% of eligible patients from Drug A to Drug B?","What clinical, economic and access evidence supports adding Drug A to the formulary?"]
def stage(n): st.session_state.stage=n
def launch(i):
    st.session_state.objective=i;st.session_state.pop('objective_choice',None);stage(0);go('HEOR & Formulary')
def evidence():
    st.subheader('Define your assessment')
    i=st.radio('Objective',range(4),format_func=lambda i:OBJECTIVES[i][0]+'  —  '+OBJECTIVES[i][1],index=st.session_state.objective,key='objective_choice');st.session_state.objective=i
    q=st.text_area('Research question or PMID',placeholder=EXAMPLES[i],key='question')
    direct=st.checkbox('Prioritize randomized trials',value=i!=3)
    if st.button('Retrieve studies',type='primary',disabled=not q.strip()):
        st.session_state.papers=[];st.session_state.queries=[]
        with st.spinner('Searching published evidence…'):
            terms=q.strip();queries=[]
            if re.fullmatch(r'\d+(?:\[PMID\])?',terms,re.I): queries=[terms.split('[')[0]+'[PMID]']
            elif '[' in terms: queries=[terms]
            else:
                drugs=[d for d in ['tirzepatide','semaglutide','liraglutide','dulaglutide','exenatide','lixisenatide'] if re.search(r'\b'+d+r'\b',q,re.I)]
                aliases={'ozempic':'semaglutide','rybelsus':'semaglutide','mounjaro':'tirzepatide','trulicity':'dulaglutide','victoza':'liraglutide'}
                drugs=list(dict.fromkeys(drugs+[v for k,v in aliases.items() if re.search(r'\b'+k+r'\b',q,re.I)]))
                if drugs: terms=' AND '.join(d+'[tiab]' for d in drugs)+' AND ("Diabetes Mellitus, Type 2"[MeSH Terms] OR "type 2 diabetes"[tiab])'
                else:
                    try:
                        ans=ask(KEY,'Return JSON object with query: sensitive PubMed Boolean query using drug and population concepts only. No outcome filters.',q);terms=ans['query'];assert isinstance(terms,str) and terms.strip()
                    except Exception as e: st.warning('AI search planning unavailable. Using PubMed natural-language search.');terms=q
                queries=[terms]
                if direct:queries.insert(0,'('+terms+') AND randomized controlled trial[pt]')
                if i in (1,3):queries.append('('+terms+') AND (cost effectiveness[tiab] OR economic[tiab] OR budget impact[tiab])')
            found={};audit=[]
            for query in queries:
                try:
                    hits=search_pubmed(query);audit.append({'query':query,'retrieved':len(hits)})
                    for p in hits:found.setdefault(p['PMID'],p)
                except Exception as e:audit.append({'query':query,'error':type(e).__name__});st.warning('PubMed request failed: '+type(e).__name__+'. Other searches will continue.')
            st.session_state.papers=list(found.values());st.session_state.queries=audit
    if st.session_state.queries:
        with st.expander('Search audit'):st.dataframe(pd.DataFrame(st.session_state.queries),hide_index=True)
    papers=st.session_state.papers
    st.caption(f'{len(papers)} retrieved records · limited search, not exhaustive')
    selected=st.multiselect('Select up to three relevant studies', [p['PMID'] for p in papers],format_func=lambda id:next(p['Title'] for p in papers if p['PMID']==id),max_selections=3)
    use_full=st.checkbox('Include accessible Europe PMC text',value=True)
    if st.button('Extract evidence and continue →',type='primary',disabled=not selected or not KEY):
        success=0
        for p in papers:
            if p['PMID'] not in selected:continue
            try:
                with st.spinner('Extracting '+p['PMID']):
                    source=p['Abstract'];url=p['URL'];label='Abstract'
                    if use_full:
                        try:
                            ft=full_text(p['PMID'])
                            if ft and ft[0]:source=source+'\n'+ft[0][:30000];url=ft[1];label='Abstract and accessible full-text paragraphs (limited; tables excluded)'
                        except Exception:st.warning('Full text unavailable; using abstract.')
                    if not source:continue
                    rows,notes=numeric_extract(KEY,p,source,url)
                    for r in rows:r['source_scope']=label; r['source_text']=source
                    st.session_state.rows=[r for r in st.session_state.rows if r['PMID']!=p['PMID']]+rows;st.session_state.notes[p['PMID']]=notes;success+=len(rows)
            except Exception as e:st.error('Extraction failed for '+p['PMID']+': '+type(e).__name__+'. Retry later.')
        if success:stage(1);st.rerun()
        else:st.warning('No numerical evidence extracted.')
    for p in papers:
        with st.expander(p['Title']):
            st.caption(p['Design']);st.write(p['Abstract']);st.markdown(f"[PubMed source]({p['URL']})")

def review():
    st.subheader('Review extracted findings')
    if not st.session_state.rows:st.info('Retrieve and extract studies first.');return
    df=pd.DataFrame(st.session_state.rows)
    a,b,c=st.columns(3);a.metric('Studies',df.PMID.nunique());b.metric('Extracted outcomes',len(df));c.metric('Reviewed values',int(df.reviewed.sum()))
    for (pmid,outcome,unit,measure,weeks),group in df.dropna(subset=['weeks','unit','measure','outcome']).groupby(['PMID','outcome','unit','measure','weeks']):
        if len(group)>1:
            st.markdown(f'**{outcome}**');st.caption(f'PMID {pmid} · {measure} · {weeks} weeks · draft values')
            fig=px.bar(group,x='arm',y='value',color='arm',color_discrete_sequence=['#16877c','#426eaa','#7765a0','#c28a39'],labels={'value':unit,'arm':'Treatment'},text_auto=True);fig.update_layout(showlegend=False);st.plotly_chart(fig,use_container_width=True)
    with st.expander('Comparison table',expanded=True):
        st.dataframe(df[['PMID','arm','outcome','value','unit','measure','weeks','reviewed']],hide_index=True,use_container_width=True)
    st.caption('Confirm the value, dose, outcome definition and source context. Matching text alone is not verification.')
    for i,r in enumerate(st.session_state.rows):
        with st.expander(f"{r['arm']} · {r['outcome']} · {r['value']} {r['unit']}"):
            st.write(r['quote']);st.markdown(f"[Original source]({r['source']})");st.caption(f"{r['measure']} · {r['weeks']} weeks · {r['source_scope']} · estimand: {r['estimand']}")
            from engine import passage_status
            status=passage_status(r.get('quote'),r.get('source_text',''))
            if status=='Exact source match':st.success(status)
            elif status=='Partial source match':st.warning(status+' — review the complete passage.')
            else:st.warning('Source not located automatically. Review the publication or supply a documented passage.')
            with st.expander('Search retrieved source text'):
                st.text(r.get('source_text','Source text unavailable; open original publication.'))
            tag=f"{r['PMID']}_{i}_{r['outcome']}"
            if status!='Exact source match':
                manual=st.text_area('Correct supporting passage (verbatim)',value=r.get('manual_quote',''),key='mq'+tag)
                reference=st.text_input('Source URL and page/table/section',value=r.get('manual_reference',''),key='mr'+tag)
                r['manual_quote']=manual;r['manual_reference']=reference
                manual_ok=bool(manual.strip() and reference.strip())
            else:manual_ok=False
            r['passage_match']=status=='Exact source match'
            r['reviewed']=st.checkbox('I verified the value, treatment, units and interpretation against the source',value=bool(r['reviewed']),key='review'+tag,disabled=not (r['passage_match'] or manual_ok)) and (r['passage_match'] or manual_ok)
            r['manual_verified']=bool(r['reviewed'] and manual_ok)
            if r['outcome']=='HbA1c':
                est=st.text_input('Reported estimand (if known)',value=str(r.get('estimand') or 'unknown'),key='est'+tag)
                ref=st.text_input('Estimand source and supporting methods passage',value=r.get('estimand_reference',''),key='er'+tag)
                r['estimand']=est.strip() if ref.strip() else 'unknown';r['estimand_reference']=ref
    st.download_button('Export evidence CSV',pd.DataFrame(st.session_state.rows).drop(columns=['source_text'],errors='ignore').to_csv(index=False),'theravalue_evidence.csv','text/csv')
    with st.expander('Evidence limitations'):
        for pmid,notes in st.session_state.notes.items():
            st.markdown('**PMID '+str(pmid)+'**')
            for note in (notes if isinstance(notes,list) else [notes]):
                if isinstance(note,str):st.write('• '+note)
                elif isinstance(note,dict):
                    for k,v in note.items():st.write(str(k).replace('_',' ').capitalize()+': '+str(v))
        st.caption('Missing information is not evidence of absence. Review the full publication.')
    if st.session_state.page=='HEOR & Formulary':
        a,b=st.columns(2);a.button('← Back to retrieval',on_click=stage,args=(0,));b.button('Continue to analysis →',type='primary',on_click=stage,args=(2,))

def economics():
    st.subheader('Trial-matched medication cost analysis')
    rows=[r for r in st.session_state.rows if r['reviewed'] and (r['passage_match'] or r.get('manual_verified')) and r['outcome']=='HbA1c' and r['unit']=='pp']
    pairs=[(a,b) for a in rows for b in rows if compatible(a,b)]
    if not pairs:
        st.warning('No eligible pair for incremental clinical analysis.')
        st.write(f'{len(rows)} verified HbA1c rows available.')
        if len(rows)<2:st.info('Approve at least two HbA1c results from the same trial in Verify. Correct unmatched passages there if necessary.')
        else:st.info('Check that the two treatment arms have the same outcome definition, units, population, follow-up and documented estimand.')
        if any(str(r.get('estimand')).lower() in ('unknown','none','') for r in rows):st.info('Estimand missing: consult the full publication and analysis methods. Do not assume that unknown estimands match.')
        st.button('← Review evidence',on_click=stage,args=(1,));return
    a,b=st.selectbox('Select comparison',pairs,format_func=lambda p:f"{p[0]['arm']} vs {p[1]['arm']} · PMID {p[0]['PMID']}")
    perspective=st.selectbox('Cost basis',['Patient out-of-pocket','Cash price','Payer net cost','Acquisition benchmark'])
    ca=st.number_input('Intervention supply cost ($)',min_value=0.,value=None);da=st.number_input('Intervention supply days',min_value=1,value=None);sa=st.text_input('Intervention cost source and date')
    cb=st.number_input('Comparator supply cost ($)',min_value=0.,value=None);db=st.number_input('Comparator supply days',min_value=1,value=None);sb=st.text_input('Comparator cost source and date')
    confirmed=st.checkbox('Confirm same cost basis, currency year and dose-specific costs; values are signed changes from baseline.')
    if None not in (ca,cb,da,db) and sa.strip() and sb.strip() and confirmed:
        effect=b['value']-a['value'];r=incremental(ca,cb,da,db,a['weeks'],effect);
        cols=st.columns(3)
        for col,k in zip(cols,['Incremental cost','Additional HbA1c reduction (pp)','Cost per additional pp']):col.metric(k, f'{r[k]:,.2f}' if r[k] is not None else 'Not applicable')
        st.dataframe(pd.DataFrame([r]),hide_index=True)
        st.caption('Medication expenditure only; constant prices and continuous therapy assumed. Not a QALY-based cost-effectiveness analysis. Differences are calculated from extracted arm means, not adjusted treatment contrasts.')
        sens=[]
        for m in [.8,1,1.2]:sens.append({'Intervention price multiplier':m,**incremental(ca*m,cb,da,db,a['weeks'],effect)})
        st.plotly_chart(px.line(pd.DataFrame(sens),x='Intervention price multiplier',y='Incremental cost',markers=True),use_container_width=True)
        if st.button('Save assessment'):st.session_state.reports.append({'type':'Trial-matched cost analysis','evidence':[a,b],'perspective':perspective,'inputs':[ca,da,sa,cb,db,sb],'results':r,'sensitivity':sens})

def budget():
    st.subheader('Annual pharmacy budget impact')
    st.caption('Documented scenario inputs; medication expenditure only, constant prices and full persistence.')
    a,b=st.columns(2);base=a.number_input('Current therapy cost per 28 days ($)',min_value=0.,value=None);new=b.number_input('Alternative therapy cost per 28 days ($)',min_value=0.,value=None)
    src=st.text_input('Cost sources, perspective and currency year');n=st.number_input('Eligible patients',min_value=1,value=1000);uptake=st.slider('Switching proportion (%)',0,100,20)
    if base is not None and new is not None and src.strip():
        old=n*base*365/28;change=n*uptake/100*(new-base)*365/28;st.metric('Annual expenditure change',f'${change:,.0f}');st.plotly_chart(px.bar(x=['Current','Scenario'],y=[old,old+change],labels={'x':'Scenario','y':'Annual USD'},color_discrete_sequence=['#426eaa']),use_container_width=True)
        if st.button('Save budget scenario'):st.session_state.reports.append({'type':'Budget impact','cost_source':src,'current_28d':base,'alternative_28d':new,'population':n,'uptake_percent':uptake,'annual_change':change});st.success('Saved in this session.')

def clinical():
    st.title('Clinical medication review');st.caption('Hypothetical adult type 2 diabetes cases only. Research prototype, not prescribing advice.')
    a,b=st.columns(2);goal=a.multiselect('Treatment priorities',['Glycemic control','Weight management','Cardiovascular risk','Kidney disease','Affordability','Tolerability']);hba=b.number_input('Current HbA1c (%) if known',min_value=3.,max_value=20.,value=None)
    meds=st.text_input('Current therapies and previous intolerance (no identifiers)');conditions=st.multiselect('Relevant history',['ASCVD','Heart failure','CKD','Pancreatitis','Severe gastrointestinal disease','Personal/family MTC or MEN2','Pregnancy','Insulin or sulfonylurea use','Unknown']);access=st.selectbox('Access concern',['Unknown','Coverage restrictions','High out-of-pocket cost','Administration preference','None reported']);options=st.text_input('Therapies being considered')
    if st.button('Generate review checklist',type='primary'):
        profile={'priorities':goal,'HbA1c':hba,'medications':meds,'history':conditions,'access':access,'options':options};st.session_state.clinical_profile=profile
    if 'clinical_profile' in st.session_state:
        p=st.session_state.clinical_profile;st.subheader('Assessment priorities')
        for title,body in [('Clinical goals',', '.join(p['priorities']) or 'Clarify treatment goals'),('Safety review','Verify current product labeling for the selected therapies; review reported history: '+(', '.join(p['history']) or 'Not provided')),('Medication review',p['medications'] or 'Confirm current medications and previous intolerance'),('Access and affordability',p['access']+' — verify plan-specific coverage and actual patient cost')]:
            with st.container(border=True):st.markdown('**'+title+'**');st.write(body)
        st.markdown('[Current prescribing information — DailyMed](https://dailymed.nlm.nih.gov/dailymed/) · [ADA standards](https://professional.diabetes.org/standards-of-care)')
        if st.button('Find supporting clinical evidence →',type='primary'):
            st.session_state.question=' '.join([p['options'],'type 2 diabetes',*p['priorities']]);launch(0);st.rerun()
        if st.button('Save clinical review'):st.session_state.reports.append({'type':'Clinical information checklist','profile':p});st.success('Saved in this session.')

if page=='Overview':
    st.markdown('<div class="hero"><div class="eyebrow">RESEARCH EDITION / TYPE 2 DIABETES</div><h1>Clinical &amp; Pharmacoeconomic Research</h1><p>Comparative effectiveness, medication expenditure and formulary review.</p></div>',unsafe_allow_html=True)
    st.subheader('Start an assessment')
    for j in (0,2):
        for col,i in zip(st.columns(2),range(j,j+2)):
            with col:
                with st.container(border=True):
                    st.subheader(OBJECTIVES[i][0]);st.markdown(f'<span style="color:#426eaa">{OBJECTIVES[i][1]}</span>',unsafe_allow_html=True);st.button('Start →',key=f'home{i}',on_click=launch,args=(i,),type='primary')
    with st.container(border=True):st.subheader('Review a clinical case');st.caption('Organize patient factors, safety questions and access considerations.');st.button('Start clinical review →',on_click=go,args=('Clinical Review',))
elif page=='HEOR & Formulary':
    st.title('HEOR & Formulary');cols=st.columns(3)
    for i,(col,name) in enumerate(zip(cols,['1 · Retrieve','2 · Verify','3 · Analyze'])):col.button(name,on_click=stage,args=(i,),type='primary' if st.session_state.stage==i else 'secondary',use_container_width=True)
    if st.session_state.stage==0:
        evidence()
        if st.session_state.objective==2:
            st.button('Skip literature search — enter budget inputs →',on_click=stage,args=(2,))
    elif st.session_state.stage==1:review()
    else:
        objective=st.session_state.objective
        if objective==1:economics()
        elif objective==2:budget()
        else:
            st.subheader('Clinical comparison' if objective==0 else 'Formulary evidence summary')
            verified=[{k:v for k,v in r.items() if k!='source_text'} for r in st.session_state.rows if r.get('reviewed')]
            if verified:
                st.dataframe(pd.DataFrame(verified)[['PMID','arm','outcome','value','unit','measure','weeks']],hide_index=True)
                st.caption('Study-specific findings; no cross-trial pooling or treatment ranking.')
            else:st.info('No verified clinical findings yet. Return to Verify to review the extracted evidence.')
            if objective==3:
                economic_notes=st.text_area('Published economic findings and citations')
                access_notes=st.text_area('Coverage, restrictions and access sources')
                conclusion=st.text_area('Reviewer assessment and uncertainties')
                if st.button('Save formulary review'):st.session_state.reports.append({'type':'Formulary review','evidence':verified,'economic_notes':economic_notes,'access_notes':access_notes,'assessment':conclusion});st.success('Saved in this session.')
            elif verified and st.button('Save clinical comparison'):st.session_state.reports.append({'type':'Clinical comparison','evidence':verified});st.success('Saved in this session.')
            st.button('← Review evidence',on_click=stage,args=(1,))
        st.button('View saved assessments →',on_click=go,args=('My Assessments',))
elif page=='Clinical Review':clinical()
elif page=='Evidence Library':
    st.title('Evidence library');review()
elif page=='My Assessments':
    st.title('My assessments');st.caption('Session only; export before leaving.')
    if not st.session_state.reports:st.info('No saved assessments yet.')
    for i,r in enumerate(st.session_state.reports):
        with st.expander(f"{i+1} · {r['type']}"):
            st.json(r);st.download_button('Export reproducible assessment',json.dumps(r,indent=2,default=str),f'assessment_{i+1}.json',key=f'dl{i}')
else:
    st.title('Research methods');st.write('Independent PubMed retrieval, optional accessible Europe PMC paragraphs, Groq extraction, human verification and deterministic medication expenditure. Manual reference data is not embedded.')
    st.warning('Research prototype. No validated prescribing recommendations, automated plan coverage, full cost-utility model, persistent storage or formal validation. Published economic studies can be retrieved but require manual interpretation.')
