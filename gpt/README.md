Experiments with using GPT for supporting semantic parsing
==========================================================

This folder contains a small program for performing GPT api calls from a command line

    gpt.py
    
and several experimental system prompts for various tasks, including

* logifyprompt3.txt : a large multishot prompt converting English to logic
* simplelogify.txt : a naive zero-shot prompt converting English to logic
* simplifyprompt1.txt : a naive zero-shot prompt  for simplifying NL text
* genprompt5.txt: a multishot prompt for determining suitable quantification
* coreferenceprompt1.txt: a multishot prompt for solving coreference tasks

Additionally we provide several regression tests as python files, containing 
a list of problems with expected answers:

* llm_core_test.py : LLM-oriented subset/modification of the core_test.py
* core_test.py : core regression test problems for the pipeline
* llm_allen_test.py : LLM-oriented subset of the allen_test.py
* allen_test.py : regression tests inspired by the Allen AI Proofwriter
* hans_test.py : a representative sample of problems from the HANS test set

Here are the results of running GPT4 and GPT3.5 on these:

* llm4_core_test_results.txt : GPT4 results on the test set llm_core_test.txt
* llm3_core_test_results.txt : GPT3.5 results on the test set llm_core_test.txt
* llm4_allen_test_results.txt : GPT4 results on the test set llm_core_test.txt
* llm3_allen_test_results.txt : GPT3.5 results on the test set llm_core_test.txt
* llm4_hans_test_results.txt : GPT4 results on the test set llm_core_test.txt
* llm3_hans_test_results.txt : GPT3.5 results on the test set llm_core_test.txt

NB! The file logifyprompt3.txt does not generate exactly the same representation
as nlpsolver uses. Instead, it uses a somewhat simpler and more abstract format,
which is quite similar to the one used by nlpsolver and should be convertable
relatively easily.

Before running gpt.py you have to create a file 

    secrets.js
    
in this folder, containing just 

    {"gpt_key": "put your GPT api key here"}    

Then try out

    ./gpt.py 4 -s logifyprompt3.txt "Elephants are big. John is an elephant."
    
and then run ./gpt.py without arguments to see available keys and options.
