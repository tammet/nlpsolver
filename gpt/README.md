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

NB! The file logifyprompt3.txt does not generate exactly the same representation
as nlpsolver uses. Instead, it uses a somewhat simpler and more abstract format,
which is quite similar to the one used by nlpsolver and should be convertable
relatively easily.

Before running gpt.py you have to replace the word "yourkeystring" with your
own GPT API key in the file

    secrets.js
    
originally containing just 

    {"gpt_key": "yourkeystring"}

Then try out

    ./gpt.py 4 -s logifyprompt3.txt "Elephants are big. John is an elephant."
    
and then run ./gpt.py without arguments to see available keys and options.
