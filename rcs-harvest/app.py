import os
import io
import json
import boto3
import requests
import logging

from lambda_multiprocessing import Pool
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

import boto3

RCS_CONFIG_PATH = os.environ['RCS_CONFIG_PATH']
GCS_TABLE       = os.environ['GCS_TABLE']
GEOCORE_ID_API  = os.environ['GEOCORE_ID_API']

def lambda_handler(event, context):
    """
    AWS Lambda Entry
    """
    
    rcs_configuration_path = RCS_CONFIG_PATH
    viewer_configuration_table = GCS_TABLE
    geocore_api_path = GEOCORE_ID_API

    id = None
    lang = None
    message = ""

    try:
        id = str(event["id"])
    except:
        message += "id was not supplied or is invalid"

    try:
        lang = str(event["lang"])
    except:
        message += ", lang was not supplied or is invalid"
    
    try:
        if (str(event["metadata"]).upper() == 'TRUE'):
            metadata = True
        else:
            metadata = False
    except:
        metadata = False

    if not id or not lang:
        response = {"message": message}
        return response
        
    id_list = id.split(',')
    
    required = [False, False, metadata]
    keys = ["gcs", "rcs", "metadata"]
    message_obj = []
    response_obj = []
    message_list = {}
    configuration = [viewer_configuration_table, rcs_configuration_path, geocore_api_path]
    
    
    iterable_pool_data = [(id_list ,lang, True, viewer_configuration_table, 'gcs'), 
                          (id_list, lang, True, rcs_configuration_path, 'rcs'),
                          (id_list, lang, metadata, geocore_api_path, 'metadata')]
    
    with Pool() as p:
        response = p.starmap(get_generic, iterable_pool_data)
    
    for i in range(0, len(keys)):
        message_obj.append(json.loads(response[i][1]))
        response_obj.append(response[i][0])
    
    for item in message_obj:
        message_list.update(item)
        
    combined_dict = {key: value for key, value in zip(keys, response_obj)}
    
    """
    Generate API response
    """

    response = {
        "headers": {"Content-type": "application/json"},
        "statusCode": "200",
        "id": id,
        "message": message_list,
        "response": combined_dict
    }
    return response


def get_generic(id_list, lang, required, path, key):
    message = ""
    response = ""
    if key == "rcs":
        #Note: RCS already supports the ability to return multiple ids from a single request
        response = {}
        lang_list = ['en', 'fr']
        for lang in lang_list:
            id = ",".join(id_list)
            rcs_url_request = path + "/" + lang + "/" + id
            headers = {'Accept': 'application/json'}
            rcs_response = requests.get(rcs_url_request, headers=headers)

            if rcs_response.ok:
                response[lang] = json.loads(rcs_response.text)
                
                if not response:
                    message = '{"rcs": "RCS not found"}'
                else:
                    message = '{"rcs": "Success returning RCS"}'
            else:
                message += '{"rcs": "Could not access RCS: ' + rcs_url_request + '"}'
    elif key == "gcs":
        #Note: GCS is obtained from a dynamodb table
        gcs_list = []
        try:
            for id in id_list:
                gcs_response = read_configuration_by_id(id, path, 'ca-central-1', dynamodb=None)
                if gcs_response == []:
                    response = json.loads("[]")
                    message = '{"gcs": "GCS not found"}'
                else:
                    try:
                        json_data = json.loads(gcs_response[0]['plugins'])
                        try:
                            gcs_list.append(json_data[0]['RAMPS'])
                        except KeyError:
                            try:
                                gcs_list.append(json_data[0])
                            except KeyError:
                                gcs_list.append(json_data)
        
                    except KeyError:
                        response = json.loads("[]")
                        message = '{"gcs": "GCS does not have valid plugins"}'
            
            if gcs_list != []:
                response = gcs_list
                message = '{"gcs": "Success returning GCS"}'
            else:
                response = json.loads("[]")
                message = '{"gcs": "GCS not found"}'
        except:
            response = json.loads("[]")
            message = '{"gcs": "Error returning GCS"}'
    elif key == "metadata":
        metadata_list = []
        if required == True:
            for id in id_list:
                metadata_url_request = path + "?lang=" + lang + "&id=" + id
                headers = {'Accept': 'application/json'}
                metadata_response = requests.get(metadata_url_request, headers=headers)
            
                if metadata_response.ok:
                    try:
                        temp = json.loads(metadata_response.text)['body']['Items']
                        metadata_list.append(temp)
                    except (KeyError, TypeError) as e:
                        response = json.loads("[]")
                        message = '{"metadata": "Metadata not found"}'
                else:
                    response = json.loads("[]")
                    message = '{"metadata": "Could not access metadata: ' + metadata_url_request + '"}'
            
            response = metadata_list
            message = '{"metadata": "Success returning metadata"}'
        else:
            response = json.loads("[]")
            message = '{"metadata": "Metadata not requested"}'

    return response, message
    

def read_configuration_by_id(uuid, viewer_configuration_table, region, dynamodb=None):
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb', region_name=region)

    table = dynamodb.Table(viewer_configuration_table)
    try:
        response = table.query(
            KeyConditionExpression=Key('uuid').eq(uuid)
        )
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        return response['Items']

# Wrapper to safely load json objects in case it is null
def nonesafe_loads(obj):
    if obj is not None:
        return json.loads(obj)