#!/usr/bin/env python
#coding=utf-8

# Todo：接口自动化测试
# Author：归根落叶
# Blog：http://this.ispenn.com

import json
import http.client,mimetypes
from urllib.parse import urlencode
import random
import time
import re
import logging
import os,sys
try:
    import xlrd
except:
    os.system('pip install -U xlrd')
    import xlrd
try:
    from pyDes import *
except ImportError as e:
    os.system('pip install -U pyDes --allow-external pyDes --allow-unverified pyDes')
    from pyDes import *
import hashlib
import base64
import smtplib  
from email.mime.text import MIMEText 

log_file = os.path.join(os.getcwd(),'log/liveappapi.log')
log_format = '[%(asctime)s] [%(levelname)s] %(message)s'
logging.basicConfig(format=log_format,filename=log_file,filemode='w',level=logging.DEBUG)
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
formatter = logging.Formatter(log_format)
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

#获取并执行测试用例
def runTest(testCaseFile):
    testCaseFile = os.path.join(os.getcwd(),testCaseFile)
    if not os.path.exists(testCaseFile):
        logging.error('测试用例文件不存在！！！')
        sys.exit()
    testCase = xlrd.open_workbook(testCaseFile)
    table = testCase.sheet_by_index(0)
    errorCase = []
    correlationDict = {}
    correlationDict['${hashPassword}'] = hash1Encode('123456')
    correlationDict['${session}'] = None
    for i in range(1,table.nrows):
        correlationDict['${randomEmail}'] = ''.join(random.sample('abcdefghijklmnopqrstuvwxyz',6)) + '@automation.test'
        correlationDict['${randomTel}'] = '186' + str(random.randint(10000000,99999999))
        correlationDict['${timestamp}'] = int(time.time())
        if table.cell(i,10).value.replace('\n','').replace('\r','') != 'Yes':
            continue
        num = str(int(table.cell(i,0).value)).replace('\n','').replace('\r','')
        api_purpose = table.cell(i,1).value.replace('\n','').replace('\r','')
        api_host = table.cell(i,2).value.replace('\n','').replace('\r','')
        request_url = table.cell(i,3).value.replace('\n','').replace('\r','')
        request_method = table.cell(i,4).value.replace('\n','').replace('\r','')
        request_data_type = table.cell(i,5).value.replace('\n','').replace('\r','')
        request_data = table.cell(i,6).value.replace('\n','').replace('\r','')
        encryption = table.cell(i,7).value.replace('\n','').replace('\r','')
        check_point = table.cell(i,8).value
        correlation = table.cell(i,9).value.replace('\n','').replace('\r','').split(';')
        for key in correlationDict:
            if request_url.find(key) > 0:
                request_url = request_url.replace(key,str(correlationDict[key]))
        if request_data_type == 'Form':
            dataFile = request_data
            if os.path.exists(dataFile):
                fopen = open(dataFile,encoding='utf-8')
                request_data = fopen.readline()
                fopen.close()
            for keyword in correlationDict:
                if request_data.find(keyword) > 0:
                    request_data = request_data.replace(keyword,str(correlationDict[keyword]))
            try:
                if encryption == 'MD5':
                    request_data = json.loads(request_data)
                    status,md5 = getMD5(api_host,urlencode(request_data).replace("%27","%22"))
                    if status != 200:
                        logging.error(num + ' ' + api_purpose + "[ " + str(status) + " ], 获取md5验证码失败！！！")
                        continue
                    request_data = dict(request_data,**{"sign":md5.decode("utf-8")})
                    request_data = urlencode(request_data).replace("%27","%22")
                elif encryption == 'DES':
                    request_data = json.loads(request_data)
                    request_data = urlencode({'param':encodePostStr(request_data)})
                else:
                    request_data = urlencode(json.loads(request_data))
            except Exception as e:
                logging.error(num + ' ' + api_purpose + ' 请求的数据有误，请检查[Request Data]字段是否是标准的json格式字符串！')
                continue
        elif request_data_type == 'Data':
            dataFile = request_data
            if os.path.exists(dataFile):
                fopen = open(dataFile,encoding='utf-8')
                request_data = fopen.readline()
                fopen.close()
            for keyword in correlationDict:
                if request_data.find(keyword) > 0:
                    request_data = request_data.replace(keyword,str(correlationDict[keyword]))
            request_data = request_data.encode('utf-8')
        elif request_data_type == 'File':
            dataFile = request_data
            if not os.path.exists(dataFile):
                logging.error(num + ' ' + api_purpose + ' 文件路径配置无效，请检查[Request Data]字段配置的文件路径是否存在！！！')
                continue
            fopen = open(dataFile,'rb')
            data = fopen.read()
            fopen.close()
            request_data = '''
------WebKitFormBoundaryDf9uRfwb8uzv1eNe
Content-Disposition:form-data;name="file";filename="%s"
Content-Type:
Content-Transfer-Encoding:binary

%s
------WebKitFormBoundaryDf9uRfwb8uzv1eNe--
    ''' % (os.path.basename(dataFile),data)
        status,resp = interfaceTest(num,api_purpose,api_host,request_url,request_data,check_point,request_method,request_data_type,correlationDict['${session}'])
        if status != 200:
            errorCase.append((num + ' ' + api_purpose,str(status),'http://'+api_host+request_url,resp))
            continue
        for j in range(len(correlation)):
            param = correlation[j].split('=')
            if len(param) == 2:
                if param[1] == '' or not re.search(r'^\[',param[1]) or not re.search(r'\]$',param[1]):
                    logging.error(num + ' ' + api_purpose + ' 关联参数设置有误，请检查[Correlation]字段参数格式是否正确！！！')
                    continue
                value = resp
                for key in param[1][1:-1].split(']['):
                    try:
                        temp = value[int(key)]
                    except:
                        try:
                            temp = value[key]
                        except:
                            break
                    value = temp
                correlationDict[param[0]] = value
    return errorCase

# 接口测试
def interfaceTest(num,api_purpose,api_host,request_url,request_data,check_point,request_method,request_data_type,session):  
    headers = {'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8',
               'X-Requested-With':'XMLHttpRequest',
               'Connection':'keep-alive',
               'Referer':'http://' + api_host,
               'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/43.0.2357.134 Safari/537.36'}
    if session is not None:
        headers['Cookie'] = 'session=' + session
        if request_data_type == 'File':
            headers['Content-Type'] = 'multipart/form-data;boundary=----WebKitFormBoundaryDf9uRfwb8uzv1eNe;charset=UTF-8'
        elif request_data_type == 'Data':
            headers['Content-Type'] = 'text/plain; charset=UTF-8'

    conn = http.client.HTTPConnection(api_host)
    if request_method == 'POST':
        conn.request('POST',request_url,request_data,headers=headers)
    elif request_method == 'GET':
        conn.request('GET',request_url+'?'+request_data,headers=headers)
    else:
        logging.error(num + ' ' + api_purpose + ' HTTP请求方法错误，请确认[Request Method]字段是否正确！！！')
        return 400,request_method
    response = conn.getresponse()
    status = response.status
    resp = response.read()
    if status == 200:
        resp = resp.decode('utf-8')
        if re.search(check_point,str(resp)):
            logging.info(num + ' ' + api_purpose + ' 成功, ' + str(status) + ', ' + str(resp))
            return status,json.loads(resp)
        else:
            logging.error(num + ' ' + api_purpose + ' 失败！！！, [ ' + str(status) + ' ], ' + str(resp))
            return 2001,resp
    else:
        logging.error(num + ' ' + api_purpose + ' 失败！！！, [ ' + str(status) + ' ], ' + str(resp))
        return status,resp.decode('utf-8')

#获取md5验证码
def getMD5(url,postData):
    headers = {'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8',
               'X-Requested-With':'XMLHttpRequest'}
    conn = http.client.HTTPConnection('this.ismyhost.com')
    conn.request('POST','/get_isignature',postData,headers=headers)
    response = conn.getresponse()
    return response.status,response.read()

# hash1加密
def hash1Encode(codeStr):
    hashobj = hashlib.sha1()
    hashobj.update(codeStr.encode('utf-8'))
    return hashobj.hexdigest()

# DES加密
def desEncode(desStr):
    k = des('secretKEY', padmode=PAD_PKCS5)
    encodeStr = base64.b64encode(k.encrypt(json.dumps(desStr)))
    return encodeStr

# 字典排序
def encodePostStr(postData):
    keyDict = {'key':'secretKEY'}
    mergeDict = dict(postData, **keyDict)
    mergeDict = sorted(mergeDict.items())
    postStr = ''
    for i in mergeDict:
        postStr = postStr + i[0] + '=' + i[1] + '&'
    postStr = postStr[:-1]
    hashobj = hashlib.sha1()
    hashobj.update(postStr.encode('utf-8'))
    token = hashobj.hexdigest()
    postData['token'] = token
    return desEncode(postData)

#发送通知邮件
def sendMail(text):
    sender = 'no-reply@myhost.cn'  
    receiver = ['penn@myhost.cn']
    mailToCc = ['penn@myhost.cn']
    subject = '[AutomantionTest]接口自动化测试报告通知'  
    smtpserver = 'smtp.exmail.qq.com'  
    username = 'no-reply@myhost.cn'  
    password = 'password'  
    
    msg = MIMEText(text,'html','utf-8')      
    msg['Subject'] = subject  
    msg['From'] = sender
    msg['To'] = ';'.join(receiver)
    msg['Cc'] = ';'.join(mailToCc)
    smtp = smtplib.SMTP()  
    smtp.connect(smtpserver)  
    smtp.login(username, password)  
    smtp.sendmail(sender, receiver + mailToCc, msg.as_string())  
    smtp.quit() 

def main():
    errorTest = runTest('TestCase/TestCasePre.xlsx')
    if len(errorTest) > 0:
        html = '<html><body>接口自动化定期扫描，共有 ' + str(len(errorTest)) + ' 个异常接口，列表如下：' + '</p><table><tr><th style="width:100px;">接口</th><th style="width:50px;">状态</th><th style="width:200px;">接口地址</th><th>接口返回值</th></tr>'
        for test in errorTest:
            html = html + '<tr><td>' + test[0] + '</td><td>' + test[1] + '</td><td>' + test[2] + '</td><td>' + test[3] + '</td></tr>'
        html = html + '</table></body></html>'
        #sendMail(html)

if __name__ == '__main__':
    main()
