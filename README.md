# Viewer Configuration Service (VCS)

The Viewer Configuration Service (VCS) is a part of the GEO.ca project that allows for viewer configuration management in GeoView.

## Table of Contents
- [Notional Architecture](#notional-architecture)
- [Features](#features)
- [API Endpoints](#api-endpoints)
  - [GET Request](#get-request)
    - [Example](#example)
  - [POST Request](#post-request)
    - [Expected Response for POST Request](#expected-response-for-post-request)
    - [Example](#example-1)
    - [Postman Example](#postman-example)

## Notional Architecture
<img width="1179" alt="gcs" src="https://github.com/Canadian-Geospatial-Platform/geocore-gcs/assets/18405829/57996a2b-3f58-4fe6-aea2-0666a33cac91">

## Features
- Handles GET and POST requests for retrieving and submitting configurations.

## API Endpoints

https://geocore.api.geo.ca/vcs?

## GET Request
Retrieve viewer configuration data:
```bash
GET /vcs?id=XYZ&lang=XYZ&metadata=false
```

### Example
```bash
curl -X GET "https://geocore.api.geo.ca/vcs?lang=en&id=21b821cf-0f1c-40ee-8925-eab12d357668&metadata=true"
```

## POST Request
Submit a viewer configuration:
```bash
POST /vcs

{
  "method": "POST",
  "body": {
    "id": "XYZ",
    "gcs": [{}]
  }
}
```

### Expected Response for POST Request
When you submit a POST request to the `/vcs` endpoint, the server will respond with a JSON similar to below. A successful response will look like this:

```bash
{
    "headers": {
        "Content-type": "application/json"
    },
    "method": "POST",
    "statusCode": 201,
    "body": {
        "message": "Inserted supplied data for id: XYZ"
    }
}
```

### Example
```bash

curl --location 'https://geocore.api.geo.ca/vcs' \
--header 'Content-Type: application/json' \
--data '{
    "method": "POST",
    "body": {
        "id": "21b821cf-0f1c-40ee-8925-eab12d357668",
        "gcs": [{
            "en": {
                "packages": {
                    "geochart": {
                        "layers": {
                            "layerId": "rcs.21b821cf-0f1c-40ee-8925-eab12d357668.en/0/1",
                            "propertyValue": "OBJECTID",
                            "propertyDisplay": "Location_Emplacement"
                        },
                        "chart": "line",
                        "query": {
                            "type": "esriRegular",
                            "url": "https://maps-cartes.services.geo.ca/server_serveur/rest/services/HC/airborne_radioactivity_en/MapServer/3",
                            "queryOptions": {
                                "whereClauses": [{
                                    "field": "Location_Emplacement",
                                    "prefix": "'\''",
                                    "valueFrom": "Location_Emplacement",
                                    "suffix": "'\''"
                                }],
                                "orderByField": "CollectionStart_DebutPrelevement"
                            }
                        },
                        "geochart": {
                            "xAxis": {
                                "type": "time",
                                "property": "CollectionStart_DebutPrelevement",
                                "label": "Collected date"
                            },
                            "yAxis": {
                                "type": "linear",
                                "property": "Activity_Activite_mBqm3",
                                "label": "Activity (mBqm3)",
                                "tooltipSuffix": "mBqm3"
                            },
                            "borderWidth": 1
                        },
                        "category": {
                            "property": "Radionuclide_Radionucleide",
                            "usePalette": false
                        },
                        "ui": {
                            "xSlider": {
                                "display": true
                            },
                            "ySlider": {
                                "display": true
                            },
                            "stepsSwitcher": true,
                            "resetStates": true,
                            "description": "This is a description text",
                            "download": true
                        }
                    }
                }
            },
            "fr": {
                "packages": {
                    "geochart": {
                        "layers": {
                            "layerId": "rcs.21b821cf-0f1c-40ee-8925-eab12d357668.en/0/1",
                            "propertyValue": "OBJECTID",
                            "propertyDisplay": "Location_Emplacement"
                        },
                        "chart": "line",
                        "query": {
                            "type": "esriRegular",
                            "url": "https://maps-cartes.services.geo.ca/server_serveur/rest/services/HC/airborne_radioactivity_en/MapServer/3",
                            "queryOptions": {
                                "whereClauses": [{
                                    "field": "Location_Emplacement",
                                    "prefix": "'\''",
                                    "valueFrom": "Location_Emplacement",
                                    "suffix": "'\''"
                                }],
                                "orderByField": "CollectionStart_DebutPrelevement"
                            }
                        },
                        "geochart": {
                            "xAxis": {
                                "type": "time",
                                "property": "CollectionStart_DebutPrelevement",
                                "label": "Collected date"
                            },
                            "yAxis": {
                                "type": "linear",
                                "property": "Activity_Activite_mBqm3",
                                "label": "Activity (mBqm3)",
                                "tooltipSuffix": "mBqm3"
                            },
                            "borderWidth": 1
                        },
                        "category": {
                            "property": "Radionuclide_Radionucleide",
                            "usePalette": false
                        },
                        "ui": {
                            "xSlider": {
                                "display": true
                            },
                            "ySlider": {
                                "display": true
                            },
                            "stepsSwitcher": true,
                            "resetStates": true,
                            "description": "This is a description text",
                            "download": true
                        }
                    }
                }
            }
        }]
    }
}
```

### Postman example

![image](https://github.com/user-attachments/assets/8133bc7c-5463-4a05-861e-5e2c896ca6d5)
