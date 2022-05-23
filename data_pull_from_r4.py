from ast import Del
from distutils.command.config import config
import requests
import json
from datetime import datetime
import pandas as pd
import logging
import argparse

def read_ignore_fields(ignore_file):
    logging.info("reading ignore fields...")
    with open(ignore_file,'r') as f:
        ignore_fields = [l.strip for l in f.readlines()]
    return ignore_fields    

def read_api_config(config_file):
    logging.info("reading api tokens and endpoint url...")
    api_token_file = config_file
    with open(api_token_file,'r') as f:
        api_conf = json.load(f)

    api_key_local = api_conf['api_key_local'] # API token for local
    api_key_r4 = api_conf['api_key_r4'] # API token for R4.
    cu_local_endpoint = api_conf['local_endpoint'] # local api endpoint
    r4_api_endpoint = api_conf['r4_api_endpoint'] # R4 api endpoint
    return api_key_local, api_key_r4, cu_local_endpoint, r4_api_endpoint

def export_data_from_redcap(api_key, api_endpoint):
    logging.info("export data from " + api_endpoint)
    data = {
        'token': api_key,
        'content': 'record',
        'action': 'export',
        'format': 'json',
        'type': 'flat',
        'csvDelimiter': '',
        'rawOrLabel': 'raw',
        'rawOrLabelHeaders': 'raw',
        'exportCheckboxLabel': 'false',
        'exportSurveyFields': 'false',
        'exportDataAccessGroups': 'false',
        'returnFormat': 'json'
    }
    flag = 1
    while(flag > 0 and flag < 5):
        r = requests.post(api_endpoint,data=data)
        if r.status_code == 200:
            logging.info('HTTP Status: ' + str(r.status_code))
            data = r.json()
            return data
        else:
            logging.error('Error occured in exporting data from ' + api_endpoint)
            logging.error('HTTP Status: ' + str(r.status_code))
            logging.error(r.content)
            flag = flag + 1

def read_accepted_fields(local_data):
    local_data_df = pd.DataFrame(local_data)
    accepted_fields = local_data_df.columns
    return accepted_fields


def export_survey_queue_link(api_key, api_endpoint,record_id):
    data = {
        'token': api_key,
        'content': 'surveyQueueLink',
        'action': 'export',
        'format': 'json',
        'returnFormat': 'json',
        'record' : record_id
    }
    flag = 1
    while(flag > 0 and flag < 5):
        r = requests.post(api_endpoint,data=data)
        if r.status_code == 200:
            flag = 0
            return_url = r.content.decode("utf-8") 
            return return_url
        else:
            logging.error('Error occured in exporting survey queue link.')
            logging.error('HTTP Status: ' + str(r.status_code) + '. R4 record_id: ' + record_id)
            logging.error(r.content)
            flag = flag + 1
    return ""
    
    
    

def add_cuimc_id(r4_record,local_data_df, cuimc_id_latest, current_mapping):
    record_id = r4_record['record_id'] 
    participant_lab_id = r4_record['participant_lab_id'].strip().lower()
    first_name = r4_record['first_name'].strip().lower()
    last_name= r4_record['last_name'].strip().lower()
    date_of_birth= r4_record['date_of_birth'].strip().lower()
    empty_name_flag = (first_name == '' or  last_name == '' or date_of_birth == '')
    if local_data_df.shape[0] != 0: # not an empty local database
        if record_id in current_mapping.keys():
            cuimc_id = current_mapping[record_id] # repeated instrument record.
            r4_yn = None
        elif record_id in local_data_df['record_id'].drop_duplicates().tolist(): # map for previously pulled
            cuimc_id = local_data_df[local_data_df['record_id']==record_id]['cuimc_id'].drop_duplicates().tolist()[0]
            current_mapping[record_id] = cuimc_id
            r4_yn = None
        elif participant_lab_id != "" and participant_lab_id in local_data_df['participant_lab_id'].tolist(): # map for first time by participant_lab_id
            cuimc_id = local_data_df[local_data_df['participant_lab_id']==participant_lab_id]['cuimc_id'].drop_duplicates().tolist()[0]
            current_mapping[record_id] = cuimc_id
            r4_yn = None
        elif not empty_name_flag: 
            subset_df = local_data_df
            subset_df = subset_df[subset_df['first_name']==first_name]
            subset_df = subset_df[subset_df['last_name']==last_name]
            subset_df = subset_df[subset_df['date_of_birth']==date_of_birth]
            if subset_df.shape[0] > 0: # map for first time by name and dob
                cuimc_id = subset_df['cuimc_id'].drop_duplicates().tolist()[0]
                current_mapping[record_id] = cuimc_id
                r4_yn = None
            else:
                cuimc_id = cuimc_id_latest + 1 # generate new id for first time R4 pull.
                current_mapping[record_id] = cuimc_id
                cuimc_id_latest = cuimc_id
                r4_yn = "1"
        else: # no identifier available in R4.
            cuimc_id = None
            r4_yn = None
    else: # an empty local database
        if record_id in current_mapping.keys():
            cuimc_id = current_mapping[record_id] # repeated instrument record.
            r4_yn = None
        else: # generate new id for first time R4 pull.
            cuimc_id = cuimc_id_latest + 1
            current_mapping[record_id] = cuimc_id
            cuimc_id_latest = cuimc_id
            r4_yn = "1"
    return cuimc_id, cuimc_id_latest, r4_yn, current_mapping

def indexing_local_data(local_data):
    logging.info("indexing local dataset")
    if local_data != []:
        local_data_df = pd.DataFrame(local_data)
        # identify the fields for mapping purpose in local data
        local_data_df = local_data_df[['cuimc_id','first_local','last_local','dob','participant_lab_id','record_id']]
        local_data_df = local_data_df.rename(columns={"first_local": "first_name", "last_local": "last_name", "dob": "date_of_birth"})
        # get latest CUIMC id
        # patch 5/23 reserve the number > 10,000 for Epic imported records.
        local_data_df['cuimc_id'] = local_data_df['cuimc_id'].astype(int)
        cuimc_id_latest = local_data_df[local_data_df['cuimc_id'] < 9999][['cuimc_id']].max()[0]
        logging.info('lastest auto generated cuimc id: ' + str(cuimc_id_latest))
        # clean up the fields on both for match purpose.
        local_data_df['first_name'] = local_data_df['first_name'].str.strip().str.lower()
        local_data_df['last_name'] = local_data_df['last_name'].str.strip().str.lower()
        local_data_df['date_of_birth'] = local_data_df['date_of_birth'].str.strip().str.lower()
        local_data_df['participant_lab_id'] = local_data_df['participant_lab_id'].str.strip().str.lower()
    else:
        cuimc_id_latest = 0
        local_data_df = pd.DataFrame()
    return local_data_df, cuimc_id_latest

def clean_record(r4_record):
    # check is it a redcap_repeat_instrument
    if r4_record['redcap_repeat_instance'] != '':
        del r4_record['record_id']
        del r4_record['r4_yn']
        del r4_record['r4_survey_queue_link']
    else:
        if r4_record['r4_yn'] is None:
            del r4_record['r4_yn']
    # patch 3/30 delete redcap newly added 'survey_queue_link' field not existing in the local redcap
    del r4_record['survey_queue_link']
    # patch 5/19 delete redcap newly added 'your_or_your_childs_3' field not existing in the local redcap
    del r4_record['your_or_your_childs_3']
    return r4_record

def push_data_to_local(api_key_local, cu_local_endpoint, r4_record):
    record_id = r4_record['record_id']
    r4_record = clean_record(r4_record)
    data = {
        'token': api_key_local,
        'content': 'record',
        'action': 'import',
        'format': 'json',
        'type': 'flat',
        'overwriteBehavior': 'overwrite',
        'forceAutoNumber': 'false',
        'data': json.dumps([r4_record]),
        'returnContent': 'count',
        'returnFormat': 'json'
    }
    flag = 1
    while(flag > 0 and flag < 5):
        r = requests.post(cu_local_endpoint,data=data)
        if r.status_code == 200:
            logging.info('HTTP Status: ' + str(r.status_code))
            flag = 0
        else:
            logging.error('Error occured in importing data to ' + cu_local_endpoint)
            logging.error('HTTP Status: ' + str(r.status_code) + '. R4 record_id: ' + record_id)
            logging.error(r.content)
            flag = flag + 1

def update_local(api_key_local,api_key_r4, cu_local_endpoint, r4_api_endpoint, local_data_df, r4_data, cuimc_id_latest):
    logging.info("update local redcap...")
    current_mapping = {}
    for r4_record in r4_data:
        cuimc_id, cuimc_id_latest, r4_yn, current_mapping = add_cuimc_id(r4_record,local_data_df, cuimc_id_latest, current_mapping)
        return_url = export_survey_queue_link(api_key=api_key_r4,api_endpoint=r4_api_endpoint,record_id=r4_record['record_id'])
        if cuimc_id is not None:
            r4_record['cuimc_id'] = str(cuimc_id)
            r4_record['r4_yn'] = r4_yn # new record indicator
            r4_record['r4_survey_queue_link'] = return_url
            push_data_to_local(api_key_local,cu_local_endpoint,r4_record)
            
if __name__ == "__main__":
    # log_file = '/phi_home/cl3720/phi/eMERGE/eIV-recruitement-support-redcap/data-pull.log'
    # token_file = '/phi_home/cl3720/phi/eMERGE/eIV-recruitement-support-redcap/api_tokens.json'
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', type=str, required=True, help="file to write log",)    
    parser.add_argument('--token', type=str, required=True, help='json file with api tokens')    
    args = parser.parse_args()
    log_file = args.log
    token_file = args.token
    

    logging.basicConfig(filename=log_file, level=logging.INFO)
    now = datetime.now()
    dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
    logging.info("Current Time =" +  dt_string)

    api_key_local, api_key_r4, cu_local_endpoint, r4_api_endpoint = read_api_config(config_file = token_file)
    local_data = export_data_from_redcap(api_key_local,cu_local_endpoint)
    r4_data = export_data_from_redcap(api_key_r4,r4_api_endpoint)
    if r4_data != []:
        local_data_df, cuimc_id_latest = indexing_local_data(local_data)
        update_local(api_key_local,api_key_r4, cu_local_endpoint, r4_api_endpoint, local_data_df, r4_data, cuimc_id_latest)
    
