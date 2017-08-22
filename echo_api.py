import os, json, importlib
from requests import Session
from functools import wraps

from zeep import Client
from zeep.transports import Transport

from xmlmanip import XMLSchema

import xml.etree.ElementTree as ET


class APITestFailError(BaseException):
    pass


class ImproperlyConfigured(BaseException):
    pass


class APICallError(BaseException):
    pass


def handle_response(method):
    @wraps(method)
    def _impl(self, *method_args, **method_kwargs):
        response = method(self, *method_args, **method_kwargs)
        if "Error|" in response:
            raise APICallError(response)
        else:
            return response
    return _impl


class Settings:

    def __init__(self, secrets_location='secrets.json'):
        try:
            with open(secrets_location, 'r') as secrets:
                secrets = json.load(secrets)
            self.USERNAME = secrets['USERNAME']
            self.PASSWORD = secrets['PASSWORD']
            self.WSDL_LOCATION = secrets["WSDL_LOCATION"]
            self.ENDPOINT = secrets["ENDPOINT"]

        except FileNotFoundError:
            print("echo_api is not properly configured and will not perform as expected. You must designate a fully "
                  "defined path to your secrets file. See documentation for more information.")
            self.USERNAME = ''
            self.PASSWORD = ''
            self.WSDL_LOCATION = ''
            self.ENDPOINT = ''


class Connection:
    @handle_response
    def get_physician(self, physician_id):
        args = [self.session_id, "PhysicianDetail", "Symed", f"@PhysicianID|{physician_id}|int"]
        return self.client.service.API_GetData(*args)

    def add_physician(self, office_id, **kwargs):
        args = [self.session_id, "Locations", "Provider", "PhysicianDetail_Create", 5, f"@OfficeID|{office_id}|int"]
        result = self.client.service.API_TreeDataCommand(*args)
        if "Error|" in result:
            raise APICallError(result)
        else:
            if len(kwargs) != 0:
                physician_id = result.split("|")[1]
                return self.edit_physician(physician_id, **kwargs)
            else:
                return result

    @handle_response
    def edit_physician(self, physician_id, **kwargs):
        physician = self.get_physician(physician_id)
        schema_and_data = ET.fromstring(physician)
        for key, value in kwargs.items():
            if schema_and_data[1][0].find(key) is None:
                new_attr = ET.SubElement(schema_and_data[1][0], key)
                new_attr.text = value
            else:
                schema_and_data[1][0].find(key).text = value
        updated_schema = ET.tostring(schema_and_data)
        args = [self.session_id, "Locations", "Provider", "PhysicianDetail",
                "Symed", f"@PhysicianID|{physician_id}|int", updated_schema]
        return self.client.service.API_UpdateData(*args)

    @handle_response
    def delete_physician(self, physician_id="", office_id=""):
        if not (physician_id and office_id):
            raise APICallError("You must specify both the physician_id and office_id.")
        args = [self.session_id, "Locations", "Provider", "PhysicianDetail_Delete", 6,
                f"@PhysicianID|{physician_id}|int@OfficeID|{office_id}|int"]
        return self.client.service.API_TreeDataCommand(*args)

    def get_latest_physician(self):
        qs = "SELECT * FROM PhysicianDetail"
        schema_str = self.client.service.API_GeneralQuery(self.session_id, qs, "")
        schema = XMLSchema(schema_str)
        paths = schema.locate(PhysicianID__ne='-1')
        physicians = [schema.retrieve('__'.join(path.split('__')[:-1])) for path in paths]
        return sorted(physicians, key=lambda x: int(x['PhysicianID']), reverse=True)[0]

    @handle_response
    def get_office(self, office_id):
        args = [self.session_id, "Office", "Symed", f"@OfficeID|{office_id}|int"]
        return self.client.service.API_GetData(*args)

    @handle_response
    def add_office(self, practice_id=""):
        if not practice_id:
            raise APICallError("You must provide a practice_id with which to associate this office.")
        args = [self.session_id, "Locations", "Office", "Offices_Create", 5, f"@PracticeID|{practice_id}|int"]
        return self.client.service.API_TreeDataCommand(*args)

    @handle_response
    def delete_office(self, office_id=""):
        if not office_id:
            raise APICallError("You must specify the office_id.")
        args = [self.session_id, "Locations", "Office", "Offices_Delete", 6,
                f"@OfficeID|{office_id}|int"]
        return self.client.service.API_TreeDataCommand(*args)

    def get_latest_office(self):
        qs = "SELECT * FROM Offices"
        schema_str = self.client.service.API_GeneralQuery(self.session_id, qs, "")
        schema = XMLSchema(schema_str)
        paths = schema.locate(OfficeID__ne='-1')
        offices = [schema.retrieve('__'.join(path.split('__')[:-1])) for path in paths]
        return sorted(offices, key=lambda x: int(x['OfficeID']), reverse=True)[0]

    def get_latest_practice(self):
        qs = "SELECT * FROM Offices WHERE OfficeID = PracticeID"
        schema_str = self.client.service.API_GeneralQuery(self.session_id, qs, "")
        schema = XMLSchema(schema_str)
        paths = schema.locate(OfficeID__ne='-1')
        offices = [schema.retrieve('__'.join(path.split('__')[:-1])) for path in paths]
        return sorted(offices, key=lambda x: int(x['OfficeID']), reverse=True)[0]

    def __init__(self, settings=Settings()):
        self.endpoint = settings.ENDPOINT
        self.session = Session()
        self.client = Client(settings.WSDL_LOCATION, transport=Transport(session=self.session))
        if "Success" in self.client.service.API_Test():
            self.session_id = self.client.service.API_Login(settings.USERNAME, settings.PASSWORD).split("|")[1]
        else:
            raise APITestFailError("Test connection failed.")
