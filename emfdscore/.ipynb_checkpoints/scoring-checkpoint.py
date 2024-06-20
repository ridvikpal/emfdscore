from nltk.corpus import stopwords
nltk_stopwords = stopwords.words('english')
from sklearn.feature_extraction.stop_words import ENGLISH_STOP_WORDS
import spacy
import re, fnmatch
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
import pandas as pd
from spacy.lang.en.stop_words import STOP_WORDS
stopwords = set(list(nltk_stopwords) + list(ENGLISH_STOP_WORDS) + list(STOP_WORDS))
from collections import Counter
from emfdscore.load_mfds import *
import progressbar, time

#### BoW Scoring ####

def tokenizer(doc):
    
    '''Performs minimal preprocessing on textual document.
    Steps include tokenization, lower-casing, and 
    stopword/punctuation/whitespace removal. 
    Returns list of processed tokens'''
    
    return  [x.lower_ for x in doc if x.lower_ not in stopwords and not x.is_punct and not x.is_digit and not x.is_quote and not x.like_num and not x.is_space] 


def score_emfd(doc):
    
    '''Scores documents with the e-MFD.'''
    
    emfd_score = {k:0 for k in probabilites+senti}
    moral_words = [ emfd[token] for token in doc if token in emfd.keys() ]
    
    for dic in moral_words:
        emfd_score['care_p'] += dic['care_p']
        emfd_score['fairness_p'] += dic['fairness_p']
        emfd_score['loyalty_p'] += dic['loyalty_p']
        emfd_score['authority_p'] += dic['authority_p']
        emfd_score['sanctity_p'] += dic['sanctity_p']
        
        emfd_score['care_sent'] += dic['care_sent']
        emfd_score['fairness_sent'] += dic['fairness_sent']
        emfd_score['loyalty_sent'] += dic['loyalty_sent']
        emfd_score['authority_sent'] += dic['authority_sent']
        emfd_score['sanctity_sent'] += dic['sanctity_sent']
    
    emfd_score = {k:v/len(doc) for k,v in emfd_score.items()}
    nonmoral_words = len(doc)-len(moral_words)
    emfd_score['moral_nonmoral_ratio'] =  len(moral_words)/nonmoral_words 
    
    return emfd_score


def score_mfd(doc):
    
    '''Scores documents with the original MFD.'''
    
    mfd_score = {k:0 for k in mfd_foundations}
    moral_words = []
    for token in doc:
        for v in mfd_regex.keys():
            if mfd_regex[v].match(token):
                for f in mfd[v]:
                    mfd_score[f] += 1
    
    mfd_score = {k:v/len(doc) for k,v in mfd_score.items()}
    
    return mfd_score


def score_mfd2(doc):
    
    '''Scores documents with the MFD2.'''
    
    mfd2_score = {k:0 for k in mfd2_foundations}
    moral_words = [ mfd2[token]['foundation'] for token in doc if token in mfd2.keys() ]
    f_counts = Counter(moral_words)
    mfd2_score.update(f_counts)    
    mfd2_score = {k:v/len(doc) for k,v in mfd2_score.items()}
    
    return mfd2_score


def score_docs(csv, dic_type, num_docs):
    
    '''Wrapper function that executes functions for preprocessing and dictionary scoring. 
    dict_type specifies the dicitonary with which the documents should be scored.
    Accepted values are: [emfd, mfd, mfd2]'''
    
    nlp = spacy.load('en', disable=['ner', 'parser', 'tagger'])
    nlp.add_pipe(tokenizer, name="mfd_tokenizer")
    
    if dic_type == 'emfd':
        nlp.add_pipe(score_emfd, name="score_emfd", last=True)
    elif dic_type == 'mfd':
        nlp.add_pipe(score_mfd, name="score_mfd", last=True)
    elif dic_type == 'mfd2':
        nlp.add_pipe(score_mfd2, name="score_mfd2", last=True)
    else:
        print('Dictionary type not recognized. Available values are: emfd, mfd, mfd2')
        return 
    
    scored_docs = []
    widgets = [
        'Processed: ', progressbar.Counter(),
        ' ', progressbar.Percentage(),
        ' ', progressbar.Bar(marker='❤'),
        ' ', progressbar.Timer(),
        ' ', progressbar.ETA(),
    ]

    with progressbar.ProgressBar(max_value=num_docs, widgets=widgets) as bar:
        for i, row in csv[0].items():
            scored_docs.append(nlp(row))
            bar.update(i)

    df = pd.DataFrame(scored_docs)
    
    if dic_type == 'emfd':
        df['f_var'] = df[probabilites].var(axis=1)
        df['sent_var'] = df[senti].var(axis=1)
        
    return df

#### PAT EXTRACTION ####

def find_ent(token, entities):
    '''High level function to match tokens to NER.
    Do not include in nlp.pipe!'''
    for k,v in entities.items():
        if token in v:
            return k
        
def spaCy_NER(doc):
    include_ents = ['PERSON','NORP', 'GPE']
    entities = {ent.text:ent.text.split(' ') for ent in doc.ents if ent.label_ in include_ents}
    cc_processed = {e:{'patient_words':[], 'agent_words':[], 'attribute_words':[],
                  'patient_scores':[], 'agent_scores':[], 'attribute_scores':[]} for e in entities.keys()}
    ner_out = {'cc_processed':cc_processed, 'doc':doc, 'entities':entities}
    
    return ner_out

def extract_dependencies(ner_out):
    doc = ner_out['doc']
    cc_processed= ner_out['cc_processed']
    entities = ner_out['entities']
    
    for token in doc:
        if token not in stopwords:
            if token.dep_ == 'nsubj' or  token.dep_ == 'ROOT':
                word = token.head.text.lower()
                if word in emfd.keys():
                    try:
                        cc_processed[find_ent(token.text, entities)]['agent_words'].append(word)
                        cc_processed[find_ent(token.text, entities)]['agent_scores'].append(emfd[word])
                    except KeyError as e:
                        pass

            if token.dep_ == 'dobj':
                word = token.head.text.lower()
                if word in emfd.keys():
                    try:
                        cc_processed[find_ent(token.text, entities)]['patient_words'].append(word)
                        cc_processed[find_ent(token.text, entities)]['patient_scores'].append(emfd[word])
                    except KeyError as e:
                        pass

            if token.dep_ == 'prep':
                word = token.head.text.lower()
                if word in emfd.keys():
                    for child in token.children:
                        try:
                            cc_processed[find_ent(str(child), entities)]['patient_words'].append(word)
                            cc_processed[find_ent(str(child), entities)]['patient_scores'].append(emfd[word])
                        except:
                            pass

            if token.text == 'is':
                try:
                    children = list(token.children)
                    word = children[1].lower()
                    if word in emfd.keys():
                        cc_processed[find_ent(str(children[0]),entities)]['attribute_words'].append(word)
                        cc_processed[find_ent(str(children[0]),entities)]['attribute_scores'].append(emfd[word])
                except:
                    pass

            if token.dep_ == 'attr':
                word = token.head.text.lower()
                if word in emfd.keys():
                    for child in token.children:
                        try:
                            cc_processed[find_ent(str(child), entities)]['attribute_words'].append(word)
                            cc_processed[find_ent(str(child), entities)]['attribute_scores'].append(emfd[word])
                        except:
                            pass   

            if token.dep_ == 'conj':
                if str(doc[token.right_edge.i]) == '.' or str(doc[token.right_edge.i]) == '!' or str(doc[token.right_edge.i]) == '?':
                    word = token.head.text.lower()
                    if word in emfd.keys():
                        try:
                            cc_processed[find_ent(str(doc[token.right_edge.i-1]), entities)]['agent_words'].append(word)
                            cc_processed[find_ent(str(doc[token.right_edge.i-1]), entities)]['agent_scores'].append(emfd[word])
                        except:
                            pass 
                else:
                    word = token.head.text.lower()
                    if word in emfd.keys():
                        try:
                            cc_processed[find_ent(str(token.right_edge), entities)]['agent_words'].append(word)
                            cc_processed[find_ent(str(token.right_edge), entities)]['agent_scores'].append(emfd[word])
                        except:
                            pass 
        
    return cc_processed

def drop_ents(cc_processed):
    
    ''' Deletes entities w/out any related words.'''
    
    empty_ents = []
    for k,v in cc_processed.items():
        counter = 0
        for k1, v1 in v.items():
            counter += len(v1)
        if counter == 0:
            empty_ents.append(k)
            
    for e in empty_ents:
        cc_processed.pop(e)
        
    return cc_processed

def mean_pat(cc_processed):
    
    '''Calculates the average emfd scores for 
    words in each PAT category. 
    Returns the final dataframe for each document. 
    This frame has three columns for detected  words in each PAT category and
    10 columns for each PAT category capturing the mean emfd scores.
    '''
    
    frames = []
    for k,v in cc_processed.items():
        agent = pd.DataFrame(v['agent_scores']).mean().to_frame().T
        agent.columns = ['agent_' + str(col) for col in agent.columns]
        
        patient = pd.DataFrame(v['patient_scores']).mean().to_frame().T
        patient.columns = ['patient_' + str(col) for col in patient.columns]
        
        attribute = pd.DataFrame(v['attribute_scores']).mean().to_frame().T
        attribute.columns = ['attribute_' + str(col) for col in attribute.columns]
        
        df = pd.concat([agent, patient, attribute], axis=1)
        df['NER'] = k
        df['agent_words'] = ','.join(v['agent_words'])
        df['patient_words'] = ','.join(v['patient_words'])
        df['attribute_words'] = ','.join((v['attribute_words']))
        frames.append(df)
    
    if len(frames) == 0:
        return pd.DataFrame()
    
    return pd.concat(frames)

def pat_docs(csv,DICT_TYPE,num_docs):
    
    '''Wrapper function that calls all individual functions 
    to execute PAT extraction'''
    
    # Build spaCy pipeline
    nlp = spacy.load('en')
    nlp.add_pipe(spaCy_NER, name='NER')
    nlp.add_pipe(extract_dependencies, name='PAT extraction')
    nlp.add_pipe(drop_ents, name='drop empty entities')
    nlp.add_pipe(mean_pat, name='average PAT scores and return final df')
    
    scored_docs = []
    widgets = [
        'Processed: ', progressbar.Counter(),
        ' ', progressbar.Percentage(),
        ' ', progressbar.Bar(marker='❤'),
        ' ', progressbar.Timer(),
        ' ', progressbar.ETA(),
    ]
    
    with progressbar.ProgressBar(max_value=num_docs, widgets=widgets) as bar:
        for i, row in csv[0].items():
            scored_docs.append(nlp(row))
            bar.update(i)
            
    df = pd.concat(scored_docs)
    
    words = ['agent_words','patient_words','attribute_words']
    a_mf = [c for c in df.columns if c.startswith('agent') and c.endswith('p')]
    a_sent = [c for c in df.columns if c.startswith('agent') and c.endswith('sent')]
    
    p_scores = [c for c in df.columns if c.startswith('patient') and c.endswith('p')]
    p_sent = [c for c in df.columns if c.startswith('patient') and c.endswith('sent')]
    
    att_scores = [c for c in df.columns if c.startswith('attribute') and c.endswith('p')]
    att_sent = [c for c in df.columns if c.startswith('attribute') and c.endswith('sent')]

    return df[['NER']+words+a_mf+a_sent+p_scores+p_sent+att_scores+att_sent].sort_values('NER')