# The cache machine of nlpsolver
#
#-----------------------------------------------------------------
# Copyright 2022 Tanel Tammet (tanel.tammet@gmail.com)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#-------------------------------------------------------------------

# ==== standard libraries ====

import sys
import json
import sqlite3
import hashlib

# ==== import other source files ====

# configuration and other globals are in nlpglobals.py
from nlpglobals import *

import nlputils

# ======= code ==========


# ----------- add to caches --------------


def add_parse_to_cache(ctxt,intxt,outdata):
  if ("use_cache_flag" not in options) or not(options["use_cache_flag"]): return 
  if not cache_db_name: return
  if not intxt or not outdata: return
  if type(intxt)!=str: return  
  if type(outdata)!=str:
    outtxt=json.dumps(outdata)
    outtype="json"
  else:
    outtxt=outdata
    outtype="text" 

  try:
    conn = sqlite3.connect(cache_db_name) 
  except:
    print("Error: could not connect to the cache database",cache_db_name)
    sys.exit(0)  
  
  try:
    sql_query = """select outtxt,outtype from parse_cache where intxt=?"""
    cur = conn.cursor()
    cur.execute(sql_query,(intxt,))
    row = cur.fetchone()
  except sqlite3.OperationalError:
    #print("cache note: no cache present, trying to create the cache first")
    try:
      sql_create = """create table parse_cache 
        (id integer primary key autoincrement, intxt text, outtxt text, outtype text, 
        timestamp datetime default current_timestamp)"""
      conn.execute(sql_create)
      conn.commit()
      row=None
    except:
      print("Error: cache table creation failed")
      sys.exit(0)  
    try:
      sql_create = """create unique index parse_cache_intxt on parse_cache (intxt);"""
      conn.execute(sql_create)
      conn.commit()
      row=None
    except:
      print("Error: cache index creation failed")
      sys.exit(0)  
    nlputils.debug_print("Cache database created.")
  except:
    #print("cache note: could not check input presence in cache")
    conn.close()
    return None
  if row:
    #print("cache insert already present")
    return
  
  sql_insert = """insert into parse_cache (intxt, outtxt, outtype) values (?,?,?)"""
  conn.execute(sql_insert,(intxt,outtxt,outtype))
  conn.commit()
  conn.close() 
  nlputils.debug_print("Stanza parse cache insert done")
  return



def add_proof_to_cache(inparams,outdata):
  if ("use_cache_flag" not in options) or not(options["use_cache_flag"]): return
  if not cache_db_name: return
  if not inparams or not outdata: return
  
  # fetch file params and non-file-params from input
  intxt=make_proof_key(inparams)
  if not intxt: return

  if type(intxt)!=str: return  
  if type(outdata)!=str:
    outtxt=json.dumps(outdata)
    outtype="json"
  else:
    outtxt=outdata
    outtype="text" 

  try:
    conn = sqlite3.connect(cache_db_name) 
  except:
    print("Error: could not connect to the cache database",cache_db_name)
    sys.exit(0)  
  
  try:
    sql_query = """select outtxt,outtype from proof_cache where intxt=?"""
    cur = conn.cursor()
    cur.execute(sql_query,(intxt,))
    row = cur.fetchone()
  except sqlite3.OperationalError:
    #print("cache note: no cache present, trying to create the cache first")
    try:
      sql_create = """create table proof_cache 
        (id integer primary key autoincrement, intxt text, outtxt text, outtype text, 
        timestamp datetime default current_timestamp)"""
      conn.execute(sql_create)
      conn.commit()
      row=None
    except:
      print("Error: cache table creation failed")
      sys.exit(0)  
    try:
      sql_create = """create unique index proof_cache_intxt on proof_cache (intxt);"""
      conn.execute(sql_create)
      conn.commit()
      row=None
    except:
      print("Error: cache index creation failed")
      sys.exit(0)  
    nlputils.debug_print("Cache database created.")
  except:
    #print("cache note: could not check input presence in cache")
    conn.close()
    return None
  if row:
    #print("cache insert already present")
    return
  
  sql_insert = """insert into proof_cache (intxt, outtxt, outtype) values (?,?,?)"""
  conn.execute(sql_insert,(intxt,outtxt,outtype))
  conn.commit()
  conn.close() 
  nlputils.debug_print("proof cache insert done")
  return


def make_proof_key(inparams):
  file_params=[]
  non_file_params=[]
  i=0
  lastel_key=False
  while True:
    if i>=len(inparams): break  
    el=inparams[i]  
    i+=1
    if el and el.startswith("-"):
      lastel_key=True
      non_file_params.append(el)
      continue
    if lastel_key:
      lastel_key=False
      non_file_params.append(el)
      continue
    if i==1:
      non_file_params.append(el)
      continue
    file_params.append(el)
  #print("fileparams",file_params)
  #rint("non_file_params",non_file_params)
  hashes=[]
  for fname in file_params:
    tmp=get_file_hash(fname)
    if not tmp: return None
    hashes.append(get_file_hash(fname))
  #print("hashes",hashes)  
  paramstr=" ".join(non_file_params+hashes)
  return paramstr


def get_file_hash(fname):
  try:
    with open(fname, "rb") as f:
      file_hash = hashlib.md5()
      while True:
        chunk=f.read(8192)
        if not chunk: break
        file_hash.update(chunk)
  except:
    return None     
  return file_hash.hexdigest()

# ----- fetch from caches -----------


def get_parse_from_cache(ctxt,intxt):
  if ("use_cache_flag" not in options) or not(options["use_cache_flag"]): return None
  if not cache_db_name: return None
  if not intxt: return None
  if type(intxt)!=str: return None 

  try:
    conn = sqlite3.connect(cache_db_name) 
  except:
    return None   
  try:
    sql_query = """select outtxt,outtype from parse_cache where intxt=?"""
    cur = conn.cursor()
    cur.execute(sql_query,(intxt,))
    row = cur.fetchone()
  except:
    conn.close()
    nlputils.debug_print("Stanza parse cache query failed.")
    return None
    
  if not row: return None
  if row[1]=="text":
    out=row[0]
  else:
    out=json.loads(row[0])
  conn.close()    
  if out:
    nlputils.debug_print("Stanza parse obtained from cache")
  return out  


def get_proof_from_cache(ctxt,inparams):
  if ("use_cache_flag" not in options) or not(options["use_cache_flag"]): return None
  if not cache_db_name: return None
  if not inparams: return None
  intxt=make_proof_key(inparams)
  if not intxt: return None
  if type(intxt)!=str: return None 
  try:
    conn = sqlite3.connect(cache_db_name) 
  except:
    return None   
  try:
    sql_query = """select outtxt,outtype from proof_cache where intxt=?"""
    cur = conn.cursor()
    cur.execute(sql_query,(intxt,))
    row = cur.fetchone()
  except:
    conn.close()
    nlputils.debug_print("GK proof cache query failed.")
    return None
    
  if not row: return None
  if row[1]=="text":
    out=row[0]
  else:
    out=json.loads(row[0])
  conn.close()    
  if out:
    nlputils.debug_print("GK proof obtained from cache")
  return out  


# --------- clear caches -------------------


def clear_parse_cache(ctxt):
  if not cache_db_name: return

  try:
    conn = sqlite3.connect(cache_db_name) 
  except:
    return  
  
  sql = """delete from parse_cache;"""    
  try:   
    cur = conn.cursor()
    cur.execute(sql)
  except:
    print("Error: cache clearing failed.")
    sys.exit(0)
  conn.close()
  return

def clear_proof_cache(ctxt):
  if not cache_db_name: return

  try:
    conn = sqlite3.connect(cache_db_name) 
  except:
    return  
  
  sql = """delete from proof_cache;"""    
  try:   
    cur = conn.cursor()
    cur.execute(sql)
  except:
    print("Error: cache clearing failed.")
    sys.exit(0)
  conn.close()
  return



# =========== the end ==========
