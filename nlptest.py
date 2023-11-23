#!/usr/bin/env python3

# Tests of the nlpsolver system.
#
# Run the program and it will run all the tests
# here and return the results.
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

import sys, subprocess, time
#import os, multiprocessing

# ==== import answer_question from nlpsolver ====

from nlpsolver import answer_question 

# ======== configuration ======

test_files=["tests_core.py","tests_hans.py","tests_allen.py"]
#test_files=["tests_allen.py"]
#test_files=["tests_dev.py"]

#test_files=["problems/babi/ajut.txt"]

#test_files=["problems/babi/ajut2.py"]

show_tests=False # set to False to suppress printing of all tests during work
show_compact=True # if show_tests is False, set to True to get 0/1 char for each test

strict_confidences=False # set to True to not accept uncertain (with confidence below 1) answers

# NB! Multiple processes are not currently implemented

processes=4 # number of parallel processes run
# processes=int(multiprocessing.cpu_count() / 2) # comment out to set your own default number of proc
outfilebase="testres" # only for multiple processes

# ======== testing program ======


def main():
  global test_files
  if len(sys.argv)>1:    
    test_files=[]
    for el in sys.argv[1:]:
      if el in ["-help","--help"]:
        print("Give .py format test files as arguments to suppress the default selection of test files")
        return
      test_files.append(el)    
  alltests=[]
  for testfile in test_files:
    try:
      f=open(testfile,"r")
      s=f.read()
    except:
      print("Could not read test file",testfile)  
      return
    try:  
      tests=eval(s)
    except BaseException as err:
      print("Error parsing test file",testfile)
      print()
      raise(err)
      return
    alltests.append([testfile,tests])  

  allresults=[] 
  for test in alltests:  
    print("\n=== running test "+test[0]+" ===\n")
    results=single_run_tests(test[1],0,len(test[1]))
    allresults.append(results)

  if len(alltests)>1:
    sum_realtestcount=0
    sum_lenokresults=0
    sum_failedresults=[]
    for result in allresults:
      sum_realtestcount+=result[0]
      sum_lenokresults+=result[1]
      sum_failedresults+=result[2]
    print("\n=== Summary for all tests ===\n")
    print("Tests run:",sum_realtestcount)
    print("OK tests:",sum_lenokresults)
    print("Failed tests:",len(sum_failedresults))
    if len(sum_failedresults)>0:
      print()
      print("Tests which failed:")
      for result in sum_failedresults:
        print("Input:",result[0][0])
        print("Expected:",result[0][1])
        print("Received:",result[1])


# dev_main() is not currently used!

def dev_main():
  #single_run_tests()
  #return
  #print("sys.argv",sys.argv) 
  #print("processes",processes) 
  if ((processes<2) or 
      ("-single" in sys.argv) or ("--single" in sys.argv) or
      len(tests)<1 or
      len(tests)<processes*2):
    # run a single process  
    #print("single")
    lower=0
    upper=len(tests)
    for i in range(0,len(sys.argv)):
      if sys.argv[i]=="-batch":
        lower=int(sys.argv[i+1])
        upper=int(sys.argv[i+2])
        outfilename=sys.argv[i+3]
        #print("lower upper outfilename",lower,upper,outfilename)
    single_run_tests(lower,upper)
  else:
    # run multiple processes
    print("Starting "+str(processes)+" test processes.")
    batchl=int(len(tests)/processes)    
    lower=0
    upper=batchl
    #print("len(tests) processes batchl",len(tests),processes,batchl)
    incr=0
    #args=sys.argv[0]+" -single"
    process_data=[]
    all_lines=[]
    # start up processes
    for i in range(0,processes):            
      if i==0: incr=0
      else : incr=batchl     
      lower=lower+incr
      upper=upper+incr
      if i==processes-1: upper=len(tests)
      outfilename=outfilebase+str(i)      
      #batchargs=args+" -batch "+str(lower)+" "+str(upper)+" "+outfilename
      outfile=open(outfilename,"w")
      batchargs=[sys.argv[0],"-single","-batch",str(lower),str(upper),outfilename]
      #print("batchargs",batchargs)
      p = subprocess.Popen(batchargs,stdout=outfile)
      incr=batchl
      process_data.append((p, outfilename))      
      #os.system(batchargs)
    # collect results  
    for p, f in process_data:
      p.wait()
      fd=open(f,"r")
      fd.seek(0)      
      lines=fd.readlines()
      #print("read lines",lines)  
      all_lines+=lines 
      #fullstr=fullstr+s
      fd.close()
      #os.remove(f)
    # merge and print
    #print("----final----")
    #print(all_lines)
    stats={"Tests run:":0,"OK tests:":0,"Failed tests:":0}    
    failmode=False
    failstr=""
    for line in all_lines:
      #print(line)
      for key in stats:
        if line.startswith(key):
          stats[key]+=int(line[len(key):])      
      if line.startswith("Tests which failed:"):
        failmode=True
      elif line.startswith("Starting to run"):
        failmode=False
      elif failmode:
        #print("failline")
        #print(line)
        failstr=failstr+line   
    print("Testing finished")
    for key in stats:
      print(key,stats[key])   
    if stats["Failed tests:"]>0:
      print()
      print("Tests which failed:")
      print(failstr)


def single_run_tests(tests, lower=0, upper=0):
  okresults=[]
  failedresults=[]
  testcount=0-1
  realtestcount=0
  print("Starting to run",len(tests),"tests")
  if show_tests: print()
  if upper==0: 
    upper=len(tests)  
  start_time = time.time() 
  for test in tests:    
    testcount+=1
    if testcount<lower: continue
    if testcount>=upper: break
    #if testcount>100: break
    realtestcount+=1
    if show_tests: print("Input:",test[0])
    try:
      result=answer_question(test[0],{"use_cache_flag":True})
    except KeyboardInterrupt:
      return  
    except:
      result="Software error."  
    #result=answer_question(test[0],False,False,False,False,True)
    if show_tests: print("Expected:",test[1])
    if show_tests: print("Received:",result) 
    if show_tests: print()   
    if okresult(test,result):
      okresults.append([test,result])
      if not show_tests and show_compact: print("1",end="",flush=True)
    else:
      failedresults.append([test,result])
      if not show_tests and show_compact: print("0",end="",flush=True)
    if testcount==1 and len(failedresults)==1 and len(tests)>100:
      print("First test failed: nlpsolver is apparently not working.")
      print("""Try ./nlpsolver.py "Elephants are animals. Elephants are animals?" to see the error message.""")
      print("Testing halted.")
      return
    if testcount==10 and len(failedresults)!=0 and len(tests)>100:
      print("One of the first ten tests failed: something is too wrong for further testing.")
      print("Testing halted.")
      print()
      break 
    #if testcount>1: break
  #if show_tests: print()
  if not show_tests and show_compact: print()
  print("Testing finished in "+str(round(time.time() - start_time,3))+" seconds")
  print("Tests run:",realtestcount)
  print("OK tests:",len(okresults))
  print("Failed tests:",len(failedresults))
  if len(failedresults)>0:
    print()
    print("Tests which failed:")
    for result in failedresults:
      print("Input:",result[0][0])
      print("Expected:",result[0][1])
      print("Received:",result[1])
  results=[realtestcount,len(okresults),failedresults]
  return results

def okresult(test,result):
  expected=test[1]
  if expected==True: expected="True."
  elif expected==False: expected="False."
  if not result:
    return False
  #print("result 1",result)
  if "(" in result and ")" in result:
    if strict_confidences: 
      result="Unknown"
    tmp=[]
    inparenthesis=False
    for char in result:      
      if char=="(": inparenthesis=True
      elif char==")": inparenthesis=False
      elif not inparenthesis:
        tmp.append(char)
    result="".join(tmp)
    result=result.replace(" .",".")
    #print("result 2",result)
  result=result.split("\n")
  result=result[0].strip()
  if expected==None:
    if result.startswith("Unknown"):
      return True
    else:
      return False  
  expected=expected.strip()  
  if expected==result:
    return True
  stdexpected=standardize_answer(expected)  
  stdresult=standardize_answer(result)
  if stdexpected==stdresult:
    return True 
  #print("test",test,"stdexpected",stdexpected)
  if (len(test)>2 and type(test[2])==list and test[2][0] in ["babi"] and 
      type(test[1])==str and test[1].lower() in result.lower()):
    return True
  return False  

def standardize_answer(txt):
  txt=txt.replace(".","")
  txt=txt.replace(","," ")
  spl=txt.split(" ")
  spl.sort()
  return spl

# ========= tests ======

dtests=[
  # obj
  ["She gave me a raise?",True],
  # iobj
  ["He teaches my daughter maths?",True],
  ["She teaches introductory logic?",True],
  ["She teaches the first-year students?",True],
  # csubj
  ["What she said makes sense?",True],
  ["What she said is interesting?",True],
  ["What she said was well received?",True],
  # ccomp
  ["He says that you like to swim?",True],
  ["He says you like to swim?",True],
  ["The boss said to start digging?",True],      
  ["We started digging?",True], # xcomp
  ["He said that he knew the muffin man?",True],
  ["""I asked : " Do you know the muffin man ? "?""",True],
  [""" " I had hoped to remain anonymous , " said the muffin man , 
     who was tracked down Sunday at his home on Drury Lane .?""",True],
  [""" " Three muffins , " he answered .?""",True],
  [""" " Three muffins , " he answered , " are all that I need today ?""",True], # parataxis 
  ["""Weapons of mass destruction , the report explained , 
    are designed to target civilian populations?""",True], # parataxis 
  ["""The impact that the group 's practices , law enforcement officials say , 
    are having on the most vulnerable within the sect?""",True], # parataxis 
  # xcomp
  ["Sue asked George to respond to her offer?",True],
  ["You look great?",True],
  ["I started to work there yesterday?",True],      
  ["I consider him a fool?",True],
  ["I consider her honest?",True],
  ["We expect them to change their minds?",True],
  ["Susan is liable to be arrested?",True],      
  ["He says that you like to swim?",True],
  ["She declared the cake beautiful .?",True],
  ["She entered the room sad?",True], # advcl
  ["Entering the room sad is not recommended ?",True], # advcl     
  ["Linda found the money walking our dog ?",True], # advcl 
  # obl
  ["Give the children the toys?",True], # iobj
  ["Give the toys to the children?",True],
  ["Last night , I swam in the pool?",True],      
  ["The cat was chased by the dog?",True],
  # vocative
  ["Guys , take it easy!",True],   
  # expl
  ["There is a ghost in the room?",True], 
  ["It is clear that we should decline ?",True], 
  ["I believe there to be a ghost in the room?",True], 
  ["I mentioned it to Mary that Sue is leaving?",True],
  # disclocated 
  ["It must not it eat , the playdough?",True],  
  # advcl 
  ["The accident happened as night was falling?",True], 
  ["If you know who did it, you should tell the teacher?",True], 
  ["He talked to him in order to secure the account?",True], 
  ["He was upset when I talked to him?",True],
  ["They heard about you missing classes?",True],   
  ["With the kids in school , I have plenty of free time?",True], 
  ["She entered the room while sad?",True], 
  ["He is a teacher , although he no longer teaches ?",True], 
  ["He is a teacher whom the students really love?",True],
  ["Entering the room sad is not recommended?",True],   
  # advmod
  ["Genetically modified food?",True], 
  ["Where do you want to go later?",True], 
  ["About 200 people came to the party?",True], 
  # discourse
  ["Iguazu is in Argentina :)",True],
  # aux
  ["Reagan has died?",True],   
  ["He should leave?",True], 
  ["Do you think that he will have left by the time we come ?",True], 
  # cop
  ["Bill is honest?",True], 
  ["Ivan is the best dancer?",True],
  ["Email usually free if you have Wifi?",True],   
  ["Sue is in shape?",True], 
  ["Sue has been helpful?",True], 
  ["The presence of troops will be destabilizing ?",True], 
  ["The important thing is to keep calm ?",True],
  # mark
  ["Forces engaged in fighting after insurgents attacked?",True],
  ["He says that you like to swim?",True],
  ["He came again , so-that the work to end to bring?",True],
  # nmod
  ["The office of the Chair is nice?",True],
  ["The Chair's office is nice?",True],
  # appos
  ["Sam , my brother , arrived?",True],
  ["Bill ( John 's cousin ) is nice?",True],
  ["The Australian Broadcasting Corporation ( ABC )?",True],
  ["Paul Mnuchin , the senior Oregon state senator?",True],
  ["The leader of the militant Lebanese Shiite group Hassan Nasrallah?",True],
  ["I met the French actor Gaspard Ulliel?",True],
  ["I met Gaspard Ulliel the French actor?",True],
  ["I met Gaspard Ulliel , the French actor?",True],
  ["I met French actor Gaspard Ulliel?",True],
  ["You can choose between four subjects , language ( German or French ) , economy , technology and art ?",True],
  ["Steve Jones Phone: 555-9814 Email: jones@abc.edf?",True],
  # nummod
  ["Sam ate 3 sheep?",True],
  ["Sam spent forty dollars?",True],
  ["Sam spent $ 40?",True],
  ["Sam ate many sheep?",True], # det
  ["The meeting will be in room 4?",True], # nmod
  ["?",True],
  ["?",True],
  ["?",True],
  ["?",True],
  ["?",True]
]  


"""
  ["",None],
  ["",None],
  ["",None],
  ["",None],
  ["",None],
  ["",None],
  ["",None],
  ["",None],
  ["",None],
  ["",None],
  ["",None],
  ["",None],
  ["",None],
  ["",None],
  ["",None],
  ["",None],
  ["",None],
"""
"John has three cars. John has two cars?"
# ========= run the program ======

if __name__ == "__main__":        
  main()  


# ========= the end =============

#https://universaldependencies.org/u/feat/

#"The strong bear quickly ate red berries in the big kitchen. The bear ate berries in a kitchen?" 
#"The strong bear quickly ate red berries in the big kitchen. A bear ate berries in a kitchen?" 

#"The bear who is big eats fish. The bear who is big eats fish?"  # bad parse
#"The bear who is red eats fish. The bear who is red eats fish?"  # ok parse
#"The bear who was red ate a fish. The bear ate a fish?"  # ok parse
#The bear who was red ate a fish. The bear who was red ate a fish?"  # ok parse
# "Bears who were nice ate. Nice bears ate?"
#"The bear who was nice ate. The bear ate?"

#"Bears who are nice eat fish who are strong. John is a nice bear. Bears who are nice eat fish?"
#"Bears who are nice eat fish who are strong. John is a nice bear. Bears who are nice eat fish who are strong?"
#"Bears who are nice eat fish who are strong. John is a nice bear. Nice bears eat strong fish?"

#"The bear who was nice ate the fish who was strong. The bear who was nice ate the fish who was strong?"
#"The bear who was nice ate the fish who was strong. The nice bear ate the strong fish?"
#"The bear who was nice ate the fish who was strong. The bear who was nice ate the fish who was red?"

#"The bear who was nice and red ate the fish who was big. The nice bear ate the big fish?"

#"If a foo is bar, it is nice. John is a foo bar. Who is nice?"
#"If a foo is bar, it is zed. Blahs are foo and bar. Who is zed?"
#"If a foo is bar and not blee, it is zed. Blahs are foo and bar. A dee is a blah. The dee is not blee. Who is zed?" 

"""
Bears want to eat
forall,[?:S3],[[isa,bear,?:S3],=>,

  [exists,[?:O4],[and,[act1,eat,?:O4,[$conf,1]],
                      [exists,[?:A5],[do2,want,?:S3,?:O4,[$conf,1],?:A5]]]]]]

  [exists,[?:O4],[and,[act1,eat,?:S3,[$conf,1]],
                      [exists,[?:A5],[do2,want,?:S3,?:O4,[$conf,1],?:A5]]]]]]                      

Bears want to eat berries
[forall,[?:S3],[[isa,bear,?:S3],=>,
  [exists,[?:O4],[and,[act1,eat,?:O4,[$conf,1]],
                      [exists,[?:A5],[do2,want,?:S3,?:O4,[$conf,1],?:A5]]]]]]
   [exists,[?:O4]                    
        [forall,[?:Aeat],
                 [and,[act2,eat,?:S3,?:O4,?:Aeat],
                      [isa,berry,?:O4,[$conf,1]] ]
                  =>    
                 [exists,[?:A5],[do2,want,?:S3,?:Aeat,[$conf,1],?:A5]]]]]]

   [exists,[?:O4]              
     [want_to_eat,S3,O4]
     [like_to_eat,S3,04]
    
     [refact2,S3,want, S3,eat,O4,Actintern,Actextern]

     S3 wants_to_eat 04

"""
"""
Wolves, foxes, birds, caterpillars, and snails are animals, and there are some of each. 
Also there are some grains, and grains are plants.

Every animal either likes to eat all plants, or, all animals much smaller than itself that like to eat some plants.

Caterpillars and snails are much smaller than birds, 
which are much smaller than foxes, which in turn are much smaller than wolves. 
Wolves do not like to eat foxes or grains, while birds like to eat caterpillars but not snails. 
Caterpillars and snails like to eat some plants.

Therefore there is an animal that likes to eat a grain-eating animal. What is it?
"""

"""
Someone who lives in Dreadbury Mansion killed Aunt Agatha.
Agatha, the butler, and Charles live in Dreadbury Mansion, and are
the only people who live therein. A killer always hates his victim,
and is never richer than his victim. Charles hates no one that Aunt
Agatha hates. Agatha hates everyone except the butler. The butler
hates everyone not richer than Aunt Agatha. The butler hates
everyone Aunt Agatha hates. No one hates everyone. Agatha is not
the butler.
Who killed Aunt Agatha?
"""

"""
Metals conduct electricity. 
Insulators do not conduct electricity. 
If thing is made of iron then it is metal. 
Nails are made of iron.
Nails conduct electricity?

Metals conduct electricity. 
Insulators do not conduct electricity. 
If something is made of iron then it is metal. 
Nails are made of plastic. 
Plastic is an insulator.
Nails conduct electricity?

Harry can do magic. 
Muggles cannot do magic. 
If a person can do magic then they can vanish. 
If a person cannot do magic then they cannot vanish. 
Mr Dursley is a Muggle.
Harry can vanish?
Mr Dursley can vanish?

If someone is not a UK resident and they do not have a UK civil service pension then they do not pay UK pension tax. 
If someone has a UK civil service pension then they pay pension tax in the UK. 
If someone is a UK resident then they pay pension tax in the UK. 
If someone's home country is UK then they are a UK resident. 
If someone's home country is France then they are a French resident. 
John's home country is UK. 
Pierre's home country is France. 
Alan's home country is France. 
Alan has a UK civil service pension.
Alan pays UK pension tax.

If you take something you shouldn't, then you are stealing.
If you are stealing, then you are doing a bad thing.
If you take something that doesn't belong to you, then you are taking something you shouldn't.
John took a book that didn't belong to him.
John was doing a bad thing?

Arthur is a bird. 
Arthur is not wounded. 
Bill is an ostrich. 
Colin is a bird. 
Colin is wounded. 
Dave is not an ostrich. 
Dave is wounded. 
If someone is an ostrich then they are a bird. 
If someone is an ostrich then they are abnormal. 
If someone is an ostrich then they cannot fly. 
If someone is a bird and wounded then they are abnormal. 
If someone is wounded then they cannot fly. 
If someone is a bird and not abnormal then they can fly.
Bill can fly?

Arthur is a bird. Arthur is not wounded. Bill is an ostrich. Colin is a bird. Colin is wounded. Dave is not an ostrich. Dave is wounded. If someone is an ostrich then they are a bird. If someone is an ostrich then they are abnormal. If someone is an ostrich then they cannot fly. If someone is a bird and wounded then they are abnormal. If someone is wounded then they cannot fly. If someone is a bird and not abnormal then they can fly. Bill can fly?

./nlpsolver.py "Arthur is a bird. Arthur is not wounded. Bill is an ostrich. Colin is a bird. Colin is wounded. Dave is not an ostrich. Dave is wounded. If someone is an ostrich then she is a bird. If someone is an ostrich then she is abnormal. If someone is an ostrich then she cannot fly. If someone is a bird and wounded then she is abnormal. If someone is wounded then she  cannot fly. If someone is a bird and not abnormal then she can fly. Birds can fly. Colin can fly?"

The circuit has a switch. 
The circuit has a bell. 
The switch is on. 
If the circuit has the switch and the switch is on then the circuit is complete. 
If the circuit does not have the switch then the circuit is complete. 
If the circuit is complete and the circuit has the light bulb then the light bulb is glowing. 
If the circuit is complete and the circuit has the bell then the bell is ringing. 
If the circuit is complete and the circuit has the radio then the radio is playing.
The bell is ringing?

./nlpsolver.py "The circuit has a switch. The circuit has a bell. The switch is on. If the circuit has the switch and the switch is on then the circuit is complete. If the circuit does not have the switch then the circuit is complete. If the circuit is complete and the circuit has the light bulb then the light bulb is glowing. If the circuit is complete and the circuit has the bell then the bell is ringing. If the circuit is complete and the circuit has the radio then the radio is playing. The bell is ringing?"

Fiona is round.
All green things are rough.
White things are not cold.
If Fiona is rough and Fiona is furry then Fiona is not big.
If Fiona is cold and Fiona is rough then Fiona is not furry.
Round things are green.
If something is round and furry then it is not big.
All furry things are big.
If something is round and not green then it is not big.
Fiona is not big.
Fiona is cold.
Fiona is not furry?

The bald eagle chases the bear.
The bear needs the bald eagle.
If someone chases the bald eagle then they do not chase the bear.
If someone needs the bald eagle then the bald eagle eats the bear.
If someone needs the bear then the bear is red.
If someone eats the bear then they are cold.
If someone is cold then they are not kind.
If someone eats the bear and they are not cold then the bear is not round.
The bald eagle is not kind?

The bald eagle chases the bear.
The bear needs the bald eagle.
If someone chases the bald eagle then they do not chase the bear.
If someone needs the bald eagle then the bald eagle eats the bear.
If someone needs the bear then the bear is red.
If someone eats the bear then they are cold.
If someone is cold then they are not kind.
If someone eats the bear and they are not cold then the bear is not round.
The bald eagle is not kind?
The bear is red?
"""