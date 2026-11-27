import streamlit as st
import pandas as pd
import plotly.express as px
import json
from engine import search_pubmed, incremental
from ai import plan, extract
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

def assistant():
    q=st.text_area('Research question (no patient identifiers)',placeholder='Compare tirzepatide and semaglutide for glycemic outcomes in adults with type 2 diabetes.')
    if st.button('Prepare evidence search',type='primary',disabled=not q.strip()):
        try:
            with st.spinner('Preparing search strategy…'): st.session_state.plan=plan(KEY,q)
        except Exception as e: st.error(str(e))
    p=st.session_state.plan
    if p:
        st.write(p.get('scope',''))
        for f in p.get('follow_up',[]): st.write('• '+str(f))
        terms=st.text_input('Review or refine PubMed query',value=str(p.get('search_terms','')))
        if st.button('Use query in evidence search'):
            st.session_state.search_terms=terms;st.session_state.page='Evidence Library';st.rerun()

def trial():
    df=pd.DataFrame({'Treatment':['Tirzepatide 5 mg','Tirzepatide 10 mg','Tirzepatide 15 mg','Semaglutide 1 mg'],'HbA1c reduction (pp)':[2.01,2.24,2.30,1.86]})
    st.caption('SURPASS-2 · 40 weeks · Published group means; not individual predictions')
    fig=px.bar(df,x='HbA1c reduction (pp)',y='Treatment',orientation='h',text_auto='.2f',color_discrete_sequence=['#24796f']);fig.update_layout(yaxis_title='',showlegend=False);st.plotly_chart(fig,use_container_width=True)
    st.markdown('[Original publication · PMID 34170647](https://pubmed.ncbi.nlm.nih.gov/34170647/)')
    return df

def search():
    q=st.text_input('PubMed search terms',value=st.session_state.search_terms,placeholder='e.g. cardiovascular outcomes')
    if st.button('Search PubMed',type='primary',disabled=not q.strip()):
        try:
            with st.spinner('Retrieving publications…'):st.session_state.papers=search_pubmed(q)
            if not st.session_state.papers:st.info('No matching publications found.')
        except Exception:st.error('PubMed retrieval failed. Please retry.')
    for p in st.session_state.papers:
        with st.expander(p['Title']):
            st.caption('PMID '+p['PMID']);st.write(p['Abstract'] or 'Abstract unavailable.');st.markdown(f"[Original source]({p['URL']})")
            if st.button('Extract evidence with AI',key='extract'+p['PMID'],disabled=not bool(p['Abstract'])):
                try:
                    with st.spinner('Extracting abstract evidence…'):st.session_state.extractions[p['PMID']]=extract(KEY,p)
                except Exception as e:st.error(str(e))
            if p['PMID'] in st.session_state.extractions:
                df=pd.DataFrame(st.session_state.extractions[p['PMID']]);st.dataframe(df,use_container_width=True,hide_index=True);st.caption('Exact passage matching is not scientific verification. Review against full text.');st.download_button('Export draft extraction',df.assign(PMID=p['PMID'],URL=p['URL']).to_csv(index=False),f"extraction_{p['PMID']}.csv",key='dl'+p['PMID'])
    if st.session_state.papers:st.download_button('Export retrieved records',pd.DataFrame(st.session_state.papers).to_csv(index=False),'pubmed_records.csv','text/csv')

if page=='Overview':
    st.markdown('<div class="hero"><div class="eyebrow">RESEARCH EDITION / TYPE 2 DIABETES</div><h1>Evidence &amp; value intelligence</h1><p>Connect clinical evidence with transparent economic analysis.</p></div>',unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader('AI-assisted research');assistant()
    a,b=st.columns(2)
    with a:
        with st.container(border=True):
            st.subheader('HEOR & Formulary');st.write('Compare published outcomes, medication costs and expenditure scenarios.');st.button('Open research workspace',on_click=go,args=('HEOR & Formulary',),type='primary')
    with b:
        with st.container(border=True):
            st.subheader('Clinical Review');st.write('Frame clinical questions and retrieve supporting evidence.');st.button('Open clinical workspace',on_click=go,args=('Clinical Review',))
    with st.container(border=True):
        st.subheader('Research spotlight');trial()
elif page=='HEOR & Formulary':
    st.title('Research assessment');task=st.selectbox('Assessment objective',['Literature review','Trial-based economic analysis','Pharmacy expenditure scenario'])
    if task=='Literature review':search()
    elif task=='Trial-based economic analysis':
        trial();dose=st.selectbox('Tirzepatide dose (mg)',[5,10,15]);effect={5:.15,10:.38,15:.44}[dose]
        st.subheader('Documented cost inputs');st.caption('Use the same cost perspective for both products. No default prices are supplied.')
        perspective=st.selectbox('Cost perspective',['Patient out-of-pocket','Cash price','Payer net cost','Acquisition benchmark'])
        a,b=st.columns(2)
        with a:
            ca=st.number_input('Tirzepatide supply cost ($)',min_value=0.,value=None);da=st.number_input('Tirzepatide supply days',min_value=1,value=None);sa=st.text_input('Tirzepatide cost source and date')
        with b:
            cb=st.number_input('Semaglutide supply cost ($)',min_value=0.,value=None);db=st.number_input('Semaglutide supply days',min_value=1,value=None);sb=st.text_input('Semaglutide cost source and date')
        verified=st.checkbox('I reviewed the sources and confirmed comparable price types and dose-specific costs.')
        if None not in (ca,cb,da,db) and sa.strip() and sb.strip() and verified:
            r=incremental(ca,cb,da,db,40,effect);a,b,c=st.columns(3);a.metric('Incremental cost',f"${r['Incremental cost']:,.2f}");b.metric('Additional mean HbA1c reduction',f'{effect:.2f} pp');c.metric('Cost per additional pp',f"${r['Cost per additional pp']:,.2f}" if r['Incremental cost']>=0 else 'Lower cost / greater effect')
            st.plotly_chart(px.bar(pd.DataFrame({'Treatment':['Tirzepatide','Semaglutide'],'40-week cost ($)':[r['Intervention cost'],r['Comparator cost']]}),x='Treatment',y='40-week cost ($)',color_discrete_sequence=['#24796f']),use_container_width=True)
            st.caption('Drug expenditure only; assumes continuous treatment and constant supply price. Does not establish overall cost-effectiveness.')
            if st.button('Save assessment'):st.session_state.reports.append({'type':task,'dose':dose,'perspective':perspective,'inputs':{'cost_a':ca,'days_a':da,'source_a':sa,'cost_b':cb,'days_b':db,'source_b':sb},'results':r,'PMID':'34170647'});st.success('Saved for this session.')
        else:st.info('Enter both documented costs, supply durations and sources to calculate results.')
    else:
        st.caption('Enter documented population and expenditure inputs. Proposed utilization is an explicit planning assumption, not observed data.')
        n=st.number_input('Eligible population',min_value=1,value=None);a=st.number_input('Current annual cost per patient ($)',min_value=0.,value=None);b=st.number_input('Alternative annual cost per patient ($)',min_value=0.,value=None);s=st.number_input('Proposed proportion shifted (%)',min_value=0.,max_value=100.,value=None);source=st.text_input('Population, price sources and scenario rationale')
        if None not in (n,a,b,s) and source.strip():
            base=n*a;future=n*((1-s/100)*a+s/100*b);st.metric('Annual expenditure change',f'${future-base:,.2f}');st.plotly_chart(px.bar(pd.DataFrame({'Scenario':['Current','Proposed'],'Annual expenditure ($)':[base,future]}),x='Scenario',y='Annual expenditure ($)',color_discrete_sequence=['#24796f']),use_container_width=True)
            st.caption('Assumes all patients initially receive the current therapy; excludes medical offsets and discontinuation.')
elif page=='Clinical Review':
    st.title('Clinical decision review');st.caption('Research support only; validated clinical rules and insurance records are not connected.')
    assistant()
elif page=='Evidence Library':
    st.title('Evidence library');t1,t2=st.tabs(['Live literature','Published trial example'])
    with t1: search()
    with t2: trial()
elif page=='My Assessments':
    st.title('My assessments');st.caption('Session storage only; export before closing the application.')
    if not st.session_state.reports:st.info('No saved assessments yet.')
    for i,r in enumerate(st.session_state.reports):
        with st.expander(f"Assessment {i+1} · {r['type']}"):st.json(r);st.download_button('Export JSON',json.dumps(r,indent=2),f'assessment_{i+1}.json',key=f'export{i}')
else:
    st.title('Methodology');st.write('Published study-level evidence; deterministic medication expenditure calculations; documented user-entered cost inputs.');st.markdown('[SURPASS-2](https://pubmed.ncbi.nlm.nih.gov/34170647/) · [PubMed E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/)');st.warning('Research prototype. Formal AI extraction validation, compatibility engine, verified insurance database, persistent storage and formal validation are pending.')
