Experiments with using GPT for supporting semantic parsing
==========================================================

This folder contains a small program for performing GPT api calls from a command line

    gpt.py
    
and several experimental system prompts for various tasks, including

* logifyprompt3.txt : a large multishot prompt converting English to logic
* simplelogify.txt : a naive zero-shot prompt converting English to logic
* simplifyprompt1.txt : a naive zero-shot prompt  for simplifying NL text
* simplifyprompt3.txt : an improved zero-shot prompt for simplifying NL text
* genprompt5.txt: a multishot prompt for determining suitable quantification
* coreferenceprompt1.txt: a multishot prompt for solving coreference tasks

Additionally we provide several regression tests as python files, containing 
a list of problems with expected answers:

* llm_core_test.py : LLM-oriented subset/modification of the core_test.py
* core_test.py : core regression test problems for the pipeline
* llm_allen_test.py : LLM-oriented subset of the allen_test.py
* allen_test.py : regression tests inspired by the Allen AI Proofwriter
* hans_test.py : a representative sample of problems from the HANS test set
* tests_wikipedia.py : a test set built from 10 typical Wikipedia articles
  tests_wikipedia_source.py: a commented file from which the test set above is built
  
Direct reasoning results of running GPT4 (gpt-4o-2024-05-13) and GPT3.5 (gpt-3.5-turbo-0125)
on these:

* llm4_core_test_results.txt : GPT4 results on the test set llm_core_test.py
* llm3_core_test_results.txt : GPT3.5 results on the test set llm_core_test.py
* llm4_allen_test_results.txt : GPT4 results on the test set llm_allen_test.py
* llm3_allen_test_results.txt : GPT3.5 results on the test set llm_allen_test.py
* llm4_hans_test_results.txt : GPT4 results on the test set hans_test.py
* llm3_hans_test_results.txt : GPT3.5 results on the test set hans_test.py
* tests_wikipedia_result.txt : GPT4 results on the test set tests_wikipedia.py

Parsing results of running GPT4 (gpt-4o-2024-05-13) as a parser on the same regression tests,
plus programmatically fixing the json and running the reasoner on the fixed versions:

* llm_tests_core1_results.txt - GPT4 raw parsing results on llm_core_test.py
* llm_tests_core1_results_converted.py - programmatically fixed json version of the parsing results above
* llm_tests_core1_parsed_solved_results.txt - reasoning results on the fixed version above

* llm_tests_allen_results.txt - GPT4 raw parsing results on llm_allen_test.py
* llm_tests_allen_results_converted.py - programmatically fixed json version of the parsing results above
* llm_tests_allen_parsed_solved_results.txt - reasoning results on the fixed version above

* llm_tests_hans_results.txt - GPT4 raw parsing results on hans_test.py
* llm_tests_hans_results_converted.py - programmatically fixed json version of the parsing results above
* llm_tests_hans_parsed_solved_results.txt - reasoning results on the fixed version above

* tests_wikipedia_parseresults.txt : GPT4 raw parsing results on tests_wikipedia1.py
* tests_wikipedia_parseresults_converted.py : programmatically fixed version of the parsing results above

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
