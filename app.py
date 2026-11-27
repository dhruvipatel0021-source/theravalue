import streamlit as st
import pandas as pd
import plotly.express as px
import json
from engine import search_pubmed, incremental
st.set_page_config(page_title='TheraValue | Research workspace',layout='wide',page_icon='📊')
st.markdown('''<style> .block-container{max-width:1180px;padding-top:2rem} [data-testid="stMetric"]{border:1px solid #dce5eb;border-radius:10px;padding:15px} h1,h2,h3{letter-spacing:-.025em} </style>''',unsafe_allow_html=True)
PAGES=['Overview','HEOR & Formulary','Clinical Review','Evidence Library','My Assessments','Methodology']
for k,v in {'page':'Overview','reports':[],'papers':[]}.items():
    if k not in st.session_state:st.session_state[k]=v
st.sidebar.markdown('## TheraValue\nEvidence & Value Intelligence')
page=st.sidebar.radio('Workspace',PAGES,key='page')
st.sidebar.caption('Research edition · Type 2 diabetes')
st.sidebar.caption('Not for clinical prescribing. Do not enter identifiable patient information.')
def go(p):st.session_state.page=p

def trial():
    df=pd.DataFrame({'Treatment':['Tirzepatide 5 mg','Tirzepatide 10 mg','Tirzepatide 15 mg','Semaglutide 1 mg'],'HbA1c reduction (pp)':[2.01,2.24,2.30,1.86]})
    st.caption('SURPASS-2 · 40 weeks · Published group means; not individual predictions')
    fig=px.bar(df,x='HbA1c reduction (pp)',y='Treatment',orientation='h',text_auto='.2f',color_discrete_sequence=['#24796f']);fig.update_layout(yaxis_title='',showlegend=False);st.plotly_chart(fig,use_container_width=True)
    st.markdown('[Original publication · PMID 34170647](https://pubmed.ncbi.nlm.nih.gov/34170647/)')
    return df

def search():
    q=st.text_input('Research question or PubMed search terms',placeholder='e.g. cardiovascular outcomes')
    if st.button('Search PubMed',type='primary',disabled=not q.strip()):
        try:
            with st.spinner('Retrieving publications…'):st.session_state.papers=search_pubmed(q)
            if not st.session_state.papers:st.info('No matching publications found.')
        except Exception as e:st.error('PubMed retrieval failed. Please retry. '+str(e))
    for p in st.session_state.papers:
        with st.expander(p['Title']):
            st.write(p['Abstract'] or 'Abstract unavailable.');st.markdown(f"[Original source]({p['URL']})")
    if st.session_state.papers:st.download_button('Export retrieved records',pd.DataFrame(st.session_state.papers).to_csv(index=False),'pubmed_records.csv','text/csv')

if page=='Overview':
    st.title('Evidence & value workspace');st.write('Evaluate clinical evidence and medication expenditure in one research workspace.')
    a,b=st.columns(2)
    with a:
        st.subheader('HEOR & Formulary Research');st.write('Retrieve evidence and evaluate clinical-economic trade-offs.');st.button('Start research assessment',on_click=go,args=('HEOR & Formulary',),type='primary')
    with b:
        st.subheader('Clinical Decision Review');st.write('Identify evidence and information required for a treatment review.');st.button('Start clinical review',on_click=go,args=('Clinical Review',))
    st.divider();st.caption('Current scope: GLP-1–based therapies in adults with type 2 diabetes.')
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
    st.title('Clinical decision review');st.info('Initial version: evidence retrieval only. Validated clinical rules and insurance records are not yet connected.')
    search()
elif page=='Evidence Library':
    st.title('Evidence library');trial();st.caption('Additional verified evidence records will be imported after workbook review.')
elif page=='My Assessments':
    st.title('My assessments');st.caption('Session storage only; export before closing the application.')
    if not st.session_state.reports:st.info('No saved assessments yet.')
    for i,r in enumerate(st.session_state.reports):
        with st.expander(f"Assessment {i+1} · {r['type']}"):st.json(r);st.download_button('Export JSON',json.dumps(r,indent=2),f'assessment_{i+1}.json',key=f'export{i}')
else:
    st.title('Methodology');st.write('Published study-level evidence; deterministic medication expenditure calculations; documented user-entered cost inputs.');st.markdown('[SURPASS-2](https://pubmed.ncbi.nlm.nih.gov/34170647/) · [PubMed E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/)');st.warning('Research prototype. AI extraction, compatibility engine, verified insurance database, persistent storage and formal validation are pending.')
