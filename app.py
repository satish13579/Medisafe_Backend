from flask import Flask,request,session
from flask.sessions import SecureCookieSessionInterface
from algosdk.v2client import indexer
import json,base64
from flask_cors import CORS
import base64
import datetime
import mysql.connector
from mysql.connector import errors
import pickle
import hashlib,os
from dotenv import load_dotenv
load_dotenv("./.env")


##### GLOBAL CONSTANTS ##########
INDEXER_ENDPOINT=os.getenv("INDEXER_ENDPOINT")
ALGOD_ENDPOINT=os.getenv("ALGOD_ENDPOINT")
APP_ID=int(os.getenv("APP_ID"))
API_KEY=os.getenv("API_KEY")
CREATOR_ADDRESS=os.getenv("CREATOR_ADDRESS")
TOKEN=os.getenv("TOKEN")
HEADERS = {
        "X-API-Key": API_KEY,
    }
DEPLOYED_URL=os.getenv("DEPLOYED_URL")
PINATA_JWT=os.getenv("PINATA_JWT")
PINATA_KEY=os.getenv("PINATA_KEY")
PINATA_SECRET_KEY=os.getenv("PINATA_SECRET_KEY")
DB_NAME=os.getenv("DB_NAME")
DB_USER=os.getenv("DB_USER")
DB_PASSWORD=os.getenv("DB_PASSWORD")
DB_HOST=os.getenv("DB_HOST")
#################################


app = Flask(__name__)
app.secret_key = 'algo-project'
CORS(app,supports_credentials=True)

@app.after_request
def set_samesite_cookie(response):
    session_cookie = SecureCookieSessionInterface().get_signing_serializer(app)
    same_cookie = session_cookie.dumps(dict(session))
    response.headers.add("Set-Cookie", f"session={same_cookie}; Secure; HttpOnly; SameSite=None; Path=/;")
    return response

def decodeB64(str:str) -> str:
    return base64.b64decode(str).decode()

def hashTuple(tup:tuple) -> str:
    tuple_str = str(tup)
    hash_object = hashlib.sha256()
    hash_object.update(tuple_str.encode('utf-8'))
    hash_hex = hash_object.hexdigest()
    return hash_hex

def get_time_left(date_string):
    # date_format = "%Y-%m-%d %H:%M:%S"
    # date_object = datetime.datetime.strptime(date_string, date_format)
    current_datetime = datetime.datetime.now()
    time_difference = (date_string + datetime.timedelta(days=1)) - current_datetime

    days, remainder = divmod(time_difference.seconds, 3600*24)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    if (date_string + datetime.timedelta(days=1))>current_datetime:
        if days > 0:
            remaining_time_str = f"{days} days, {hours} hours, {minutes} minutes, {seconds} seconds"
        elif hours >0:
            remaining_time_str = f"{hours} hours, {minutes} minutes, {seconds} seconds"
        elif minutes>0:
            remaining_time_str = f"{minutes} minutes, {seconds} seconds"
        elif seconds>0:
            remaining_time_str = f"{seconds} seconds"
        else:
            remaining_time_str = '-'
    else:
        remaining_time_str = '-'

    return remaining_time_str


indexer_client = indexer.IndexerClient(TOKEN,INDEXER_ENDPOINT, HEADERS)


class User():

    user_add=None

    def __init__(self,user_add:str) -> None:
        self.user_add = user_add
        self.is_opted = self.get_is_opted()
        if(self.is_opted):
            self.retrive_local_state()

    def get_is_opted(self) -> bool:
        user_add = self.user_add
        res=indexer_client.lookup_account_application_local_state(user_add,application_id=APP_ID)
        if len(res["apps-local-states"])>0:
            if res['apps-local-states'][0]['id']==APP_ID:
                return True
        return False
    
    def retrive_local_state(self)-> None:
        if(self.is_opted):
            res=indexer_client.lookup_account_application_local_state(self.user_add,application_id=APP_ID)
            self.local_state = dict()
            for pair in res['apps-local-states'][0]['key-value']:
                key= decodeB64(pair['key'])
                value = pair['value']['uint'] if pair['value']['type']==2 else decodeB64(pair['value']['bytes'])
                self.local_state[key]=value
        else:
            self.local_state = None
        return self.local_state
    
    def generate_request_hash(self,patient_add:str,request_type:int,note:str)->str:
        if self.retrive_local_state()!=None:
            if(self.local_state['role']=='DOCTOR'):
                previous_hash=self.local_state['reserved_local_valuerequest_hash']
                time_stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                tup = tuple([self.user_add,patient_add,request_type,note,time_stamp,previous_hash])
                return {"doctor_add":self.user_add,"patient_add":patient_add,"request_type":request_type,"note":note,
                        "time_stamp":time_stamp,"previous_hash":previous_hash,"current_hash":hashTuple(tup)}
        return None
    
    def update_request_hash(self,obj):
        if self.retrive_local_state()!=None:
            if(self.local_state['role'])=='DOCTOR':
                tup = tuple([self.user_add,obj['patient_add'],obj['request_type'],obj['note'],obj['time_stamp'],obj['previous_hash']])
                if(obj['current_hash']==self.local_state['reserved_local_valuerequest_hash']) and obj['current_hash']==hashTuple(tup):
                    con = mysql.connector.connect(host=DB_HOST , user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
                    cursor = con.cursor(buffered=False, dictionary=True)
                    q="INSERT INTO request_log (`doctor_add`,`patient_add`,`request_type`,`note`,`time_stamp`,`previous_hash`,`current_hash`) VALUES ('{}','{}','{}','{}','{}','{}','{}')".format(
                        self.user_add,obj['patient_add'],obj['request_type'],obj['note'],obj['time_stamp'],obj['previous_hash'],obj['current_hash']
                    )
                    try:
                        cursor.execute(q)
                        con.commit()
                        return True
                    except errors.IntegrityError as e:
                        return False
        return False
    
    def generate_access_hash(self,request_hash,access_status):
        if self.retrive_local_state()!=None:
            if(self.local_state['role']=='PATIENT'):
                q="SELECT * FROM request_log WHERE current_hash='{}' AND patient_add='{}'".format(request_hash,self.user_add)
                con = mysql.connector.connect(host=DB_HOST , user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
                cursor = con.cursor(buffered=False, dictionary=True)
                cursor.execute(q)
                rows=cursor.fetchall()
                if len(rows)>0:
                    row=rows[0]
                    time_stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    tup = tuple([self.user_add,row['doctor_add'],access_status,time_stamp,request_hash,self.local_state['reserved_local_valueaccess_hash']])
                    return {"patient_add":self.user_add,"doctor_add":row['doctor_add'],"access_status":access_status,"time_stamp":time_stamp,"request_hash":request_hash,"previous_hash":self.local_state['reserved_local_valueaccess_hash'],"current_hash":hashTuple(tup)}
        return None
            
    def update_access_hash(self,obj):
        if self.retrive_local_state()!=None:
            if(self.local_state['role'])=='PATIENT':
                tup = tuple([self.user_add,obj['doctor_add'],obj['access_status'],obj['time_stamp'],obj['request_hash'],obj['previous_hash']])
                if(obj['current_hash']==self.local_state['reserved_local_valueaccess_hash']) and obj['current_hash']==hashTuple(tup):
                    con = mysql.connector.connect(host=DB_HOST , user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
                    cursor = con.cursor(buffered=False, dictionary=True)
                    q="INSERT INTO access_log (`patient_add`,`doctor_add`,`access_status`,`time_stamp`,`request_hash`,`previous_hash`,`current_hash`) VALUES ('{}','{}','{}','{}','{}','{}','{}')".format(
                        self.user_add,obj['doctor_add'],obj['access_status'],obj['time_stamp'],obj['request_hash'],obj['previous_hash'],obj['current_hash']
                    )
                    try:
                        cursor.execute(q)
                        con.commit()
                        return True
                    except errors.IntegrityError as e:
                        return False
        return False
    
    def generate_data_hash(self,access_hash,access_status):
        if self.retrive_local_state()!=None:
            if(self.local_state['role']=='PATIENT'):
                q="SELECT * FROM data_log WHERE current_hash='{}' AND patient_add='{}'".format(request_hash,self.user_add)
                con = mysql.connector.connect(host=DB_HOST , user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
                cursor = con.cursor(buffered=False, dictionary=True)
                cursor.execute(q)
                rows=cursor.fetchall()
                if len(rows)>0:
                    row=rows[0]
                    time_stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    tup = tuple([self.user_add,row['doctor_add'],access_status,time_stamp,request_hash,self.local_state['reserved_local_valueaccess_hash']])
                    return {"patient_add":self.user_add,"doctor_add":row['doctor_add'],"access_status":access_status,"time_stamp":time_stamp,"request_hash":request_hash,"previous_hash":self.local_state['reserved_local_valueaccess_hash'],"current_hash":hashTuple(tup)}
        return None

    
    def get_patient_history(self):
        if self.retrive_local_state()!=None:
            if(self.local_state['role']=='PATIENT'):
                q="SELECT * FROM data_log WHERE patient_add='{}' ORDER BY id DESC".format(self.user_add)
                con = mysql.connector.connect(host=DB_HOST , user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
                cursor = con.cursor(buffered=False, dictionary=True)
                cursor.execute(q)
                rows=cursor.fetchall()
                json=[]
                i=1
                for row in rows:
                    jsonrow={}
                    jsonrow['snum']=i
                    jsonrow['past_prescription']=row['data']
                    jsonrow['addedby']=User(row['doctor_add']).local_state['name']
                    jsonrow['addedon']=row['time_stamp'].strftime("%Y-%m-%d %H:%M:%S")
                    jsonrow['attachments']=row['attachments'].decode('utf-8')
                    json.append(jsonrow)
                    i+=1
                return json
        return []
    
    def get_patient_data(self):
        if self.retrive_local_state()!=None:
            if(self.local_state['role']=='PATIENT'):
                q="SELECT * FROM data_log WHERE patient_add='{}' ORDER BY id DESC".format(self.user_add)
                con = mysql.connector.connect(host=DB_HOST , user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
                cursor = con.cursor(buffered=False, dictionary=True)
                cursor.execute(q)
                rows=cursor.fetchall()
                json=[]
                i=1
                for row in rows:
                    jsonrow={}
                    jsonrow['snum']=i
                    jsonrow['date']=row['time_stamp'].strftime("%Y-%m-%d %H:%M:%S")
                    doctor = User(row['doctor_add'])
                    jsonrow['doctorname']=doctor.local_state['name']
                    jsonrow['patient_prescription']=row['data']
                    jsonrow['patient_attachments']=row['attachments'].decode('utf-8')
                    jsonrow['doctordetails'] = doctor.local_state
                    if row['current_hash']=='' or row['current_hash']=='Null':
                        jsonrow['need_approval']=True
                        jsonrow['current_hash']=hashTuple(tuple([row['patient_add'],row['doctor_add'],row['time_stamp'],row['data'],row['attachments'],row['access_hash'],row['previous_hash']]))
                    else:
                        jsonrow['need_approval']=False
                        jsonrow['current_hash']=row['current_hash']
                    json.append(jsonrow)
                    i+=1
                return json
        return []
    
    def get_doctor_history(self,patient_add=None):
        if self.retrive_local_state()!=None:
            if(self.local_state['role']=='DOCTOR'):
                if(patient_add!=None):
                    q="SELECT * FROM data_log WHERE doctor_add='{}' AND patient_add='{}' ORDER BY id DESC".format(self.user_add,patient_add)
                else:
                    q="SELECT * FROM data_log WHERE doctor_add='{}' ORDER BY id DESC".format(self.user_add)
                con = mysql.connector.connect(host=DB_HOST , user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
                cursor = con.cursor(buffered=False, dictionary=True)
                cursor.execute(q)
                rows=cursor.fetchall()
                json=[]
                for row in rows:
                    jsonrow={}
                    jsonrow['time_stamp']=row['time_stamp']
                    jsonrow['patient_add']=row['patient_add']
                    jsonrow['data']=row['data']
                    jsonrow['attachments']=row['attachments']
                    jsonrow['patient_details']=User(row['patient_add']).local_state
                    json.append(jsonrow)
                return json
        return []

    def get_request_log(self):
        if self.retrive_local_state()!=None:
            if(self.local_state['role']=='DOCTOR'):
                pass
    

@app.route('/login',methods=['POST'])
def login():
    user_add = request.json['user_add']
    user = User(user_add=user_add)
    if(user.is_opted):
        session['user']=pickle.dumps(user)
        return json.dumps({"statusCode":200,"role":user.local_state['role'],"notify":"Login Successfull.!!"})
    else:
        return json.dumps({"statusCode":302,"href":"/register","notify":"Opt In to Our Dapp To Continue.!!"})



@app.route('/user_info',methods=['GET'])
def user_info():
    if session.get('user'):
        user = pickle.loads(session.get('user'))
        return json.dumps({"statusCode":200,"data":{"user_add":user.user_add,"is_opted":user.is_opted,"local_state":user.retrive_local_state()}})
    else:
        return json.dumps({"statusCode":302,"href":"/login","notify":"Login To Continue.!!"})
    

@app.route("/get_qr",methods=['GET'])
def get_qr():
    if session.get('user'):
        user=pickle.loads(session.get('user'))
        return json.dumps({"statusCode":200,"qr_svg":user.get_qr_code()})
    else:
        return json.dumps({"statusCode":302,"href":"/login","notify":"Login To Continue.!!"})


@app.route('/auth',methods=['GET'])
def auth():
    if session.get('user'):
        return json.dumps({"statusCode":200})
    return json.dumps({"statusCode":302,"href":"/login","notify":"Login To Continue.!!"})


@app.route('/get_scan_details',methods=['POST'])
def get_scan_details():
        if session.get('user'):
            scan_add = request.json['add']
            user=pickle.loads(session.get('user'))
            if user.retrive_local_state()!=None:
                if user.local_state['role']=='DOCTOR':
                    scan_user=User(scan_add)
                    if scan_user.local_state['role']=='PATIENT':
                        q="SELECT * FROM access_log WHERE patient_add='{}' AND doctor_add='{}' AND access_status=1 AND ADDDATE(time_stamp, INTERVAL 1 DAY)>'{}'".format(scan_user.user_add,user.user_add,datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                        con = mysql.connector.connect(host=DB_HOST , user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
                        cursor = con.cursor(buffered=False, dictionary=True)
                        cursor.execute(q)
                        rows=cursor.fetchall()
                        is_having_access = False
                        if len(rows)>0:
                            for row in rows:
                                access_hash = row['current_hash']
                                data_check_q = "SELECT * FROM data_log WHERE access_hash='{}'".format(access_hash)
                                cursor.execute(data_check_q)
                                data_rows=cursor.fetchall()
                                if(len(data_rows)==0):
                                    is_having_access=True
                                    break
                        is_having_emergency=False
                        is_pending=False
                        if not is_having_access:
                            q="SELECT * FROM request_log WHERE patient_add='{}' AND doctor_add='{}' AND request_type=2 AND ADDDATE(time_stamp, INTERVAL 1 DAY)>'{}'".format(scan_user.user_add,user.user_add,datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                            cursor.execute(q)
                            rows=cursor.fetchall()
                            if len(rows)>0:
                                for row in rows:
                                    request_hash = row['current_hash']
                                    access_check_q = "SELECT * FROM access_log WHERE request_hash='{}'".format(request_hash)
                                    cursor.execute(access_check_q)
                                    access_rows=cursor.fetchall()
                                    if(len(access_rows)>0):
                                        for access_row in access_rows:
                                            if access_row['access_status']!=0:
                                                access_hash = access_row['current_hash']
                                                data_check_q = "SELECT * FROM data_log WHERE access_hash='{}'".format(access_hash)
                                                cursor.execute(data_check_q)
                                                data_rows=cursor.fetchall()
                                                if(len(data_rows)==0):
                                                    is_having_emergency=True
                                                    break
                                    else:
                                        is_having_emergency=True
                            if not is_having_emergency:
                                q="SELECT * FROM request_log WHERE patient_add='{}' AND doctor_add='{}' ORDER BY id DESC".format(scan_user.user_add,user.user_add)
                                cursor.execute(q)
                                rows = cursor.fetchall()
                                if(len(rows)>0):
                                    row=rows[0]
                                    check="SELECT * FROM access_log WHERE patient_add='{}' AND doctor_add='{}' AND request_hash='{}'".format(row['patient_add'],row['doctor_add'],row['current_hash'])
                                    cursor.execute(check)
                                    checkss=cursor.fetchall()
                                    if(len(checkss)==0):
                                        is_pending=True
                        return json.dumps({"statusCode":200,"data":{"user_add":scan_user.user_add,"is_opted":scan_user.is_opted,"is_having_access":is_having_access,"is_having_emergency":is_having_emergency,"is_pending":is_pending,"patient_details":scan_user.retrive_local_state()}})
                    else:
                        return json.dumps({"statusCode":403,"notify":"Can't Access Doctor Profile.!!"})
                else:
                    scan_user = User(scan_add)
                    if scan_user.local_state['role']=='DOCTOR':
                        q="SELECT * FROM access_log WHERE patient_add='{}' AND doctor_add='{}' AND access_status=1 AND ADDDATE(time_stamp, INTERVAL 1 DAY)>'{}'".format(user.user_add,scan_user.user_add,datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                        con = mysql.connector.connect(host=DB_HOST , user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
                        cursor = con.cursor(buffered=False, dictionary=True)
                        cursor.execute(q)
                        rows=cursor.fetchall()
                        is_having_access = True if len(rows)>0 else False
                        if not is_having_access:
                            q="SELECT * FROM request_log WHERE patient_add='{}' AND doctor_add='{}' AND request_type=2 AND ADDDATE(time_stamp, INTERVAL 1 DAY)>'{}'".format(user.user_add,scan_user.user_add,datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                            cursor.execute(q)
                            rows=cursor.fetchall()
                            is_having_emergency=True if len(rows)>0 else False
                            if not is_having_emergency:
                                return json.dumps({"statusCode":200,"data":{"user_add":scan_user.user_add,"is_opted":scan_user.is_opted,"is_having_access":is_having_access,"is_having_emergency_access":is_having_emergency,"doctor_details":scan_user.retrive_local_state(),"doctor_records":scan_user.get_doctor_history(user.user_add)}})
                            else:
                                return json.dumps({"statusCode":200,"data":{"user_add":scan_user.user_add,"is_opted":scan_user.is_opted,"is_having_access":is_having_access,"is_having_emergency_access":is_having_emergency,"doctor_records":scan_user.get_doctor_history(user.user_add),"doctor_details":scan_user.retrive_local_state()}})
                        else:
                            return json.dumps({"statusCode":200,"data":{"user_add":scan_user.user_add,"is_opted":scan_user.is_opted,"is_having_access":is_having_access,"is_having_emergency_access":is_having_emergency,"doctor_records":scan_user.get_doctor_history(user.user_add),"doctor_details":scan_user.retrive_local_state()}})
                    else:
                        return json.dumps({"statusCode":403,"notify":"Can't Access Patient Profile.!!"})
            else:
                return json.dumps({"statusCode":302,"href":"/login","notify":"Login To Continue.!!"})      
        else:
            return json.dumps({"statusCode":302,"href":"/login","notify":"Login To Continue.!!"})
        
@app.route('/get_doctor_past',methods=['GET'])
def get_doctor_past():
    if(session.get('user')):
        user=pickle.loads(session.get('user'))

        
    else:
        return json.dumps({"statusCode":302,"href":"/login","notify":"Login To Continue.!!"})
    
@app.route('/generate_request_hash',methods=['POST'])
def generate_request_hash():
    if session.get('user'):
        doctor=pickle.loads(session.get('user'))
        if doctor.local_state['role']=='DOCTOR':
            patient_add=request.json['patient_add']
            request_type=request.json['request_type']
            note=request.json['note']
            res=doctor.generate_request_hash(patient_add,request_type,note)
            if res != None:
                return json.dumps({"statusCode":200,"obj":res})
            else:
                return json.dumps({"statusCode":500,"notify":"Something went Wrong.!!"})
        else:
            return json.dumps({"statusCode":403,"notify":"Dont have Access to This Method"})
    else:
        return json.dumps({"statusCode":302,"href":"/login","notify":"Login To Continue.!!"})

@app.route('/update_request_hash',methods=['POST'])
def update_request_hash():
    if session.get('user'):
        doctor = pickle.loads(session.get('user'))
        if doctor.local_state['role']=='DOCTOR':
            obj=request.json['obj']
            res=doctor.update_request_hash(obj)
            if(res):
                return json.dumps({"statusCode":200,"notify":"Request Sent Successfully.!!"})
            else:
                return json.dumps({"statusCode":500,"notify":"Some Unknown error Occured"})
        else:
            return json.dumps({"statusCode":403,"notify":"Dont have Access to This Method"})
    else:
        return json.dumps({"statusCode":302,"href":"/login","notify":"Login To Continue.!!"})

@app.route('/generate_access_hash',methods=['POST'])
def generate_access_hash():
    if session.get('user'):
        patient=pickle.loads(session.get('user'))
        if patient.local_state['role']=='PATIENT':
            request_hash=request.json['request_hash']
            access_status=request.json['access_status']
            res=patient.generate_access_hash(request_hash,access_status)
            if res != None:
                return json.dumps({"statusCode":200,"obj":res})
            else:
                return json.dumps({"statusCode":500,"notify":"Something went Wrong.!!"})
        else:
            return json.dumps({"statusCode":403,"notify":"Dont have Access to This Method"})
    else:
        return json.dumps({"statusCode":302,"href":"/login","notify":"Login To Continue.!!"})

@app.route('/update_access_hash',methods=['POST'])
def update_access_hash():
    if session.get('user'):
        patient = pickle.loads(session.get('user'))
        if patient.local_state['role']=='PATIENT':
            obj=request.json['obj']
            res=patient.update_access_hash(obj)
            if(res):
                return json.dumps({"statusCode":200,"notify":"Access Updated Successfully.!!"})
            else:
                return json.dumps({"statusCode":500,"notify":"Some Unknown error Occured"})
        else:
            return json.dumps({"statusCode":403,"notify":"Dont have Access to This Method"})
    else:
        return json.dumps({"statusCode":302,"href":"/login","notify":"Login To Continue.!!"})

    
    

@app.route('/doctor_access',methods=['GET'])
def doctor_access():
    if(session.get('user')):
        doctor=pickle.loads(session.get("user"))
        con = mysql.connector.connect(host=DB_HOST , user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
        cursor = con.cursor(buffered=False, dictionary=True)
        date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        json_data = []
        i=1

        q="SELECT * FROM request_log WHERE doctor_add='{}' ORDER BY id DESC".format(doctor.user_add)
        cursor.execute(q)
        rows=cursor.fetchall()
        for row in rows:
            patient = User(row['patient_add'])
            js={}
            js['sno']=i
            js['patient_add']=row['patient_add']
            js['patient_name']=patient.local_state['name']
            js['patient_dob']=patient.local_state['DOB']
            js['access_type']= 'GENERAL' if row['request_type']==1 else 'EMERGENCY'
            js['access_endson']=get_time_left(row['time_stamp'])
            if (js['access_type']!='EMERGENCY'):
                q="SELECT * FROM access_log WHERE doctor_add='{}' AND request_hash='{}'".format(doctor.user_add,row['current_hash'])
                cursor.execute(q)
                r=cursor.fetchall()
                if(len(r)>0):
                    q1="SELECT * FROM data_log WHERE doctor_add='{}' AND access_hash='{}'".format(doctor.user_add,r[0]['current_hash'])
                    cursor.execute(q1)
                    r1=cursor.fetchall()
                    if(len(r1)>0):
                        js['request_access']='completed'
                        js['access_endson']='-'
                        js['writeable']='no'
                    else:
                        if r[0]['access_status']==0:
                            js['request_access']='rejected'
                            js['access_endson']='-'
                            js['writeable']='no'
                        elif r[0]['access_status']==1 and get_time_left(r[0]['time_stamp'])!='-':
                            js['request_access']='active'
                            js['access_hash']=r[0]['current_hash']
                            js['access_endson']=get_time_left(r[0]['time_stamp'])
                            js['writeable']='yes'
                        else:
                            js['request_access']='expired'
                            js['access_endson']='-'
                            js['writeable']='no'
                else:
                    js['request_access']='pending'
                    js['access_endson']='-'
                    js['writeable']='no'
            else:
                q="SELECT * FROM access_log WHERE doctor_add='{}' AND request_hash='{}'".format(doctor.user_add,row['current_hash'])
                cursor.execute(q)
                r=cursor.fetchall()
                if(len(r)>0):
                    q1="SELECT * FROM data_log WHERE doctor_add='{}' AND access_hash='{}'".format(doctor.user_add,r[0]['current_hash'])
                    cursor.execute(q1)
                    r1=cursor.fetchall()
                    if(len(r1)>0):
                        js['request_access']='completed'
                        js['access_endson']='-'
                        js['writeable']='no'
                    else:
                        if r[0]['access_status']==0:
                            js['request_access']='rejected'
                            js['access_endson']='-'
                            js['writeable']='no'
                        elif r[0]['access_status']==1 and get_time_left(r[0]['time_stamp'])!='-':
                            js['request_access']='active'
                            js['access_hash']=r[0]['current_hash']
                            js['access_endson']=get_time_left(r[0]['time_stamp'])
                            js['writeable']='yes'
                        else:
                            js['request_access']='expired'
                            js['access_endson']='-'
                            js['writeable']='no'
                elif get_time_left(row['time_stamp'])!='-':
                    js['request_access']='active'
                    js['access_endson']=get_time_left(row['time_stamp'])
                    js['writeable']='no'
                else:
                    js['request_access']='expired'
                    js['access_endson']='-'
                    js['writeable']='no'
            if js['request_access']=='active':
                js['patient_history']=patient.get_patient_history()
            else:
                js['patient_history']=[]
            i+=1
            json_data.append(js)
        print(json_data)
        return json.dumps({"statusCode":200,"data":json_data})
    else:
        return json.dumps({"statusCode":302,"href":"/login","notify":"Login To Continue.!!"})
    
@app.route("/send_data",methods=['POST'])
def send_data():
    if session.get('user'):
        doctor=pickle.loads(session.get('user'))
        if doctor.local_state['role']=='DOCTOR':
            con = mysql.connector.connect(host=DB_HOST , user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
            cursor = con.cursor(buffered=False, dictionary=True)
            patient_add=request.json['patient_add']
            access_hash=request.json['access_hash']
            data=request.json['data']
            date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            q="SELECT * FROM access_log WHERE patient_add='{}' AND current_hash='{}' AND doctor_add='{}' AND access_status=1 AND ADDDATE(time_stamp,INTERVAL 1 DAY)>'{}'".format(patient_add,access_hash,doctor.user_add,date)
            cursor.execute(q)
            rows=cursor.fetchall()
            if len(rows)>0:
                row=rows[0]
                patient = User(patient_add)
                q="INSERT INTO data_log (`patient_add`,`doctor_add`,`time_stamp`,`data`,`attachments`,`access_hash`,`previous_hash`) VALUES('{}','{}','{}','{}','{}','{}','{}')".format(patient_add,doctor.user_add,date,data,"",access_hash,patient.local_state['reserved_local_valuedata_hash'])
                try:
                    cursor.execute(q)
                    con.commit()
                    return json.dumps({"statusCode":200})
                except errors.IntegrityError as e:
                    print(e)
                    return json.dumps({"statusCode":403,"notify":"Query Failed"})
            else:
                return json.dumps({"statusCode":403,"notify":"Malfunctioned Data"})
    else:
        return json.dumps({"statusCode":302,"href":"/login","notify":"Login To Continue.!!"})

@app.route('/patient_access',methods=['GET'])
def patient_access():
    if session.get('user'):
        patient = pickle.loads(session.get('user'))
        if patient.local_state['role']=='PATIENT':
            jsonn=patient.get_patient_data()
            print(jsonn)
            return json.dumps({"statusCode":200,'data':jsonn})
        else:
            return json.dumps({"statusCode":403,"notify":"Unauthorized Access"})
    else:
        return json.dumps({"statusCode":302,"href":"/login","notify":"Login To Continue.!!"})


@app.route('/get_request_log',methods=['GET'])
def get_request_logs():
    if session.get('user'):
        patient=pickle.loads(session.get('user'))
        if patient.local_state['role']=='PATIENT':
            con = mysql.connector.connect(host=DB_HOST , user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
            cursor = con.cursor(buffered=False, dictionary=True)
            q="SELECT * FROM request_log WHERE patient_add='{}' ORDER BY id DESC".format(patient.user_add)
            cursor.execute(q)
            rows=cursor.fetchall()
            json_data=[]
            i=1
            for row in rows:
                js={}
                js['sno']=i
                checkq="SELECT * FROM access_log WHERE patient_add='{}' AND request_hash='{}'".format(patient.user_add,row['current_hash'])
                cursor.execute(checkq)
                res=cursor.fetchall()
                if(len(res)>0):
                    if(res[0]['access_status']==0):
                        js['access_status']=0
                    else:
                        js['access_status']=1
                    js['access_given_on']=res[0]['time_stamp'].strftime("%Y-%m-%d %H:%M:%S")
                else:
                    js['access_status']=-1
                js['request_hash']=row['current_hash']
                js['doctor_name']=User(row['doctor_add']).local_state['name']
                js['date']=row['time_stamp'].strftime("%Y-%m-%d %H:%M:%S")
                js['note']=row['note']
                i+=1
                json_data.append(js)
            print(json_data)
            return json.dumps({"statusCode":200,"data":json_data})
    else:
        return json.dumps({"statusCode":302,"href":"/login","notify":"Login To Continue.!!"})
    




@app.route('/logout',methods=['GET'])
def logout():
    if session.get('user'):
        session.pop('user')
    return json.dumps({"statusCode":302,"href":"/","notify":"Logout Successfull.!!"})

    

if __name__ == '__main__':
    app.run(debug=True)