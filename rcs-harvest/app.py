import os
import json
import boto3
import base64
import binascii
import requests
import logging
import datetime

from lambda_multiprocessing import Pool
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError, NoCredentialsError

from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

RCS_CONFIG_PATH = os.environ['RCS_CONFIG_PATH']
GCS_TABLE       = os.environ['GCS_TABLE']
GEOCORE_ID_API  = os.environ['GEOCORE_ID_API']
AOS_HOST = os.environ['OS_ENDPOINT']
NEW_INDEX_NAME = os.environ['NEW_INDEX_NAME']
REGION = 'ca-central-1'

def lambda_handler(event, context):
    """
    AWS Lambda Entry
    """
    print(event)
    print(context)
    
    # Use IAM credentials instead
    credentials = boto3.Session().get_credentials()
    aws_auth = AWS4Auth(credentials.access_key, credentials.secret_key, REGION, 'es', session_token=credentials.token)

    # Initialize OpenSearch client
    os_client = OpenSearch(
        hosts=[{'host': AOS_HOST, 'port': 443}],
        http_auth=aws_auth,
        use_ssl=True,
        verify_certs=True,
        ssl_assert_hostname = False,
        ssl_show_warn = False,
        connection_class=RequestsHttpConnection
    )

    # Delete index (e.g., if index format has changed)
    #os_client.indices.delete(index=NEW_INDEX_NAME)

    # Creates new OpenSearch index - ignored if index already exists
    create_opensearch_index(os_client, NEW_INDEX_NAME)

    metadata = event.get('metadata', '') or ''
    lang = event.get('lang', '') or ''
    id = event.get('id', '') or ''
    ip_address = event.get('ip_address', '') or ''
    timestamp = event.get('timestamp', '') or ''
    user_agent = event.get('user_agent', '') or ''
    http_method = event.get('http_method', '') or ''
    referrer = event.get('referrer', '') or ''

    method = str(event["method"]).upper()

    if method == 'POST':
        return handle_post_request(event, GCS_TABLE)
    elif method == 'GET':
        get_return_json =  handle_get_request(event, RCS_CONFIG_PATH, GCS_TABLE, GEOCORE_ID_API)

        #Use ip2geo_handler to do document formating
        layer_name_en, layer_name_fr, layer_type, ip2geo_data = ip2geo_handler(os_client, get_return_json, ip_address)

        document = [
            {
                "timestamp": timestamp,
                "lang": lang,
                "id": id,
                "metadata": metadata,
                "user_agent": user_agent,
                "http_method": http_method,
                "referrer": referrer,
                "layer_name_en": layer_name_en,
                "layer_name_fr": layer_name_fr,
                "layer_type": layer_type,
                "ip2geo": ip2geo_data
            }
        ]
        save_to_opensearch(os_client, NEW_INDEX_NAME, document)

        return get_return_json        
    else:
        return {
            "headers": {"Content-type": "application/json"},
            "statusCode": 405,
            "body": json.dumps({"message": "Method Not Allowed"})
        }

def handle_post_request(event, GCS_TABLE):
    message = ""
    
    try:
        # Check if the body is Base64 encoded
        if isinstance(event["body"], str):
            if is_base64_encoded(event["body"]):
                json_bytes = base64.b64decode(event["body"])
            else:
                json_bytes = event["body"].encode('utf-8')
            json_data = json.loads(json_bytes)
        elif isinstance(event["body"], dict):
            json_data = event["body"]
        else:
            raise ValueError("Invalid body format")
        
        #print("json_data: ", json_data)
        if isinstance(json_data, str):
            json_data = json.loads(json_data)  # Parsing if it's a string
        gcs_data = json_data["body"]["gcs"]  # Extracting 'gcs' from the body
        #print("gcs_data: ", gcs_data)
    except (KeyError, json.JSONDecodeError, ValueError):
        message += "json_data was not supplied or is invalid"
        return {
            "headers": {"Content-type": "application/json"},
            "statusCode": 400,
            "body": json.dumps({"message": message})
        }
    
    id = json_data["body"]["id"]
    print("gcs_data: ", id)
    if not id:
        message += "no id was supplied or is invalid"
    else:
        create_configuration_by_id(id, GCS_TABLE, gcs_data, 'ca-central-1', dynamodb=None)
        message += f"Inserted supplied data for id: {id}"

    return {
        "headers": {"Content-type": "application/json"},
        "method": "POST",
        "statusCode": 201,
        "body": {
            "message": message,
        }
    }

def handle_get_request(event, RCS_CONFIG_PATH, GCS_TABLE, GEOCORE_ID_API):
    message = ""
    try:
        id = str(event["id"])
    except KeyError:
        message += "id was not supplied or is invalid"

    try:
        lang = str(event["lang"])
    except KeyError:
        message += ", lang was not supplied or is invalid"
    
    try:
        if str(event["metadata"]).upper() == 'TRUE':
            metadata = True
        else:
            metadata = False
    except KeyError:
        metadata = False

    if not id or not lang:
        return {"message": message}
            
    id_list = id.split(',')
    
    required = [False, False, metadata]
    keys = ["gcs", "rcs", "metadata"]
    message_obj = []
    response_obj = []
    message_list = {}
    configuration = [GCS_TABLE, RCS_CONFIG_PATH, GEOCORE_ID_API]
    
    iterable_pool_data = [(id_list, lang, True, GCS_TABLE, 'gcs'), 
                          (id_list, lang, True, RCS_CONFIG_PATH, 'rcs'),
                          (id_list, lang, metadata, GEOCORE_ID_API, 'metadata')]
    
    with Pool() as p:
        response = p.starmap(get_generic, iterable_pool_data)
    
    for i in range(len(keys)):
        message_obj.append(json.loads(response[i][1]))
        response_obj.append(response[i][0])
    
    for item in message_obj:
        message_list.update(item)
        
    combined_dict = {key: value for key, value in zip(keys, response_obj)}
    
    return {
        "headers": {"Content-type": "application/json"},
        "statusCode": 200,
        "method": "GET",
        "id": id,
        "message": message_list,
        "response": combined_dict
    }

def get_generic(id_list, lang, required, path, key):
    message = ""
    response = {}
    timeout_seconds = 5  # Set the timeout for the requests

    if key == "rcs":
        # Note: RCS already supports the ability to return multiple ids from a single request
        lang_list = ['en', 'fr']
        for lang in lang_list:
            id = ",".join(id_list)
            rcs_url_request = f"{path}/{lang}/{id}"
            headers = {'Accept': 'application/json'}
            try:
                rcs_response = requests.get(rcs_url_request, headers=headers, timeout=timeout_seconds)

                if rcs_response.ok:
                    response[lang] = json.loads(rcs_response.text)
                    message = '{"rcs": "Success returning RCS"}' if response else '{"rcs": "RCS not found"}'
                else:
                    message = f'{{"rcs": "Could not access RCS: {rcs_url_request}"}}'
            except requests.Timeout:
                response[lang] = json.loads("{}")
                message = '{"rcs": "RCS timed out"}'
            except requests.RequestException as e:
                response[lang] = json.loads("{}")
                message = '{"rcs": "RCS request exception"}'
            except:
                response[lang] = json.loads("{}")
                message = '{"rcs": "RCS not found"}'
    elif key == "gcs":
        # Note: GCS is obtained from a dynamodb table
        gcs_list = []
        try:
            for id in id_list:
                gcs_response = read_configuration_by_id(id, path, 'ca-central-1', dynamodb=None)
                if gcs_response['Items']:
                    json_data = json.loads(gcs_response['Items'][0]['plugins'])
                    gcs_list.append(json_data[0].get('RAMPS', json_data[0]))
                else:
                    response_string = f'{{"en": "{id} not found", "fr": "{id} pas trouvé"}}'
                    gcs_list.append(json.loads(response_string))
                    message = '{"gcs": "GCS not found"}'

            response = gcs_list if gcs_list else json.loads("[]")
            message = '{"gcs": "Success returning GCS"}' if gcs_list else '{"gcs": "GCS not found"}'
        except IndexError:
            response = json.loads("[]")
            message = '{"gcs": "No GCS entry found"}'
        except Exception:
            response = json.loads("[]")
            message = '{"gcs": "Error returning GCS"}'
    elif key == "metadata":
        metadata_list = []
        if required:
            for id in id_list:
                metadata_url_request = f"{path}?lang={lang}&id={id}"
                headers = {'Accept': 'application/json'}
                metadata_response = requests.get(metadata_url_request, headers=headers)

                if metadata_response.ok:
                    try:
                        temp = json.loads(metadata_response.text)['body']['Items']
                        metadata_list.append(temp)
                    except (KeyError, TypeError):
                        response = json.loads("[]")
                        message = '{"metadata": "Metadata not found"}'
                else:
                    response = json.loads("[]")
                    message = f'{{"metadata": "Could not access metadata: {metadata_url_request}"}}'

            response = metadata_list if metadata_list else json.loads("[]")
            message = '{"metadata": "Success returning metadata"}' if metadata_list else '{"metadata": "Metadata not found"}'
        else:
            response = json.loads("[]")
            message = '{"metadata": "Metadata not requested"}'

    return response, message

def read_configuration_by_id(uuid, GCS_TABLE, REGION, dynamodb=None):
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb', region_name=REGION)

    table = dynamodb.Table(GCS_TABLE)
    try:
        response = table.query(KeyConditionExpression=Key('uuid').eq(uuid))
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        return response

def create_configuration_by_id(uuid, GCS_TABLE, json_data, REGION, dynamodb=None):
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        
    dateTime = datetime.datetime.utcnow().isoformat()[:-7] + 'Z'
    
    json_string = json.dumps(json_data)
    
    table = dynamodb.Table(GCS_TABLE)
    
    response = table.put_item(
       Item={
            'uuid': uuid,
            'plugins': json_string,
            'datetime': dateTime
        }
    )
    
    if response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 200:
        print("Item added successfully.")
    else:
        print(f"Error: {response}")

def is_base64_encoded(data):
    try:
        if isinstance(data, str):
            data_bytes = data.encode('utf-8')
        elif isinstance(data, bytes):
            data_bytes = data
        else:
            return False
        
        return base64.b64encode(base64.b64decode(data_bytes)) == data_bytes
    except (binascii.Error, ValueError):
        return False

def nonesafe_loads(obj):
    if obj is not None:
        return json.loads(obj)

def parse_geo_point(ip2geo_data):
    if 'location' in ip2geo_data and isinstance(ip2geo_data['location'], str):
        try:
            lat, lon = map(float, ip2geo_data['location'].split(','))
            ip2geo_data['location'] = {"lat": lat, "lon": lon}  # Convert to geo_point format
        except ValueError:
            print("Invalid location format:", ip2geo_data['location'])
            ip2geo_data['location'] = None  # Handle errors gracefully
    return ip2geo_data

def ip2geo_handler(os_client, get_return_json, ip_address):
    try:
        layer_name_en = get_return_json['response']['rcs']['en'][0]['layers'][0]['name']
    except:
        layer_name_en = ''
    
    try:
        layer_name_fr = get_return_json['response']['rcs']['fr'][0]['layers'][0]['name']
    except:
        layer_name_fr = ''

    try:
        layer_type = get_return_json['response']['rcs']['en'][0]['layers'][0]['layerType']
    except:
        layer_type = ''
    
    ip2geo_payload = {
        "docs": [
            {
                "_index": "test",
                "_id": "1",
                "_source": {
                    "ip": ip_address
                }
            }
        ]
    }

    response = os_client.transport.perform_request(
        method="POST",
        url="/_ingest/pipeline/ip-to-geo-pipeline/_simulate",
        body=json.dumps(ip2geo_payload)
    )

    try:
        ip2geo_data = response["docs"][0]["doc"]["_source"].get("ip2geo", {})
        ip2geo_data = parse_geo_point(ip2geo_data) #ensure lat lon is a geo_point
    except (KeyError, json.JSONDecodeError) as e:
        print("Error extracting ip2geo data:", str(e))
    
    return layer_name_en, layer_name_fr, layer_type, ip2geo_data

def create_opensearch_index(os_client, index_name):
    """Create a new OpenSearch index if it doesn't exist."""
    if not os_client.indices.exists(index=index_name):
        # Define the mapping for the new index
        index_body = {
            "mappings": {
                "properties": {
                    "timestamp": {"type": "date"},
                    "lang": {"type": "keyword"},
                    "id": {"type": "keyword"},
                    "metadata": {"type": "keyword"},
                    "ip_address": {"type": "ip"},
                    "user_agent": {"type": "keyword"},
                    "http_method": {"type": "keyword"},
                    "layer_name_en": {"type": "keyword"},
                    "layer_name_fr": {"type": "keyword"},
                    "layer_type": {"type": "keyword"},
                    "referrer": {"type": "keyword"},
                    "ip2geo": {
                        "properties": {
                            "continent_name": {"type": "keyword"},
                            "region_iso_code": {"type": "keyword"},
                            "city_name": {"type": "keyword"},
                            "country_iso_code": {"type": "keyword"},
                            "country_name": {"type": "keyword"},
                            "region_name": {"type": "keyword"},
                            "location": {"type": "geo_point"},
                            "time_zone": {"type": "keyword"}
                        }
                    }
                }
            }
        }

        response = os_client.indices.create(index=index_name, body=index_body)
        print(f"Created new OpenSearch index: {index_name}")
        return response
    else:
        print(f"Index '{index_name}' already exists.")
        return None

def save_to_opensearch(os_client, index, document):
    """
    Loads the transformed log data into OpenSearch.
    """
    for doc in document:
        response = os_client.index(index=index, body=doc)