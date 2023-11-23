nlpsolver
=========

Nlpsolver is an experimental pipeline for automated reasoning in natural language,
capable of performing both natural language inference (NLI) and question answering.
The pipeline is described in the paper 
[An Experimental Pipeline for Automated Reasoning in Natural Language](https://link.springer.com/chapter/10.1007/978-3-031-38499-8_29).

The pipeline contains:
* A semantic parser from English to extended first order logic.
* A first-order logic reasoner solving the problem expressed in extended logic.
* A subsystem for converting the proof given by the reasoner to English.

Nlpsolver is developed with a goal to be (a) a backbone of our research in
combining machine learning and large language models with logic-based
symbolic reasoning, (b) using automated reasoner as an interface
between natural language and external tools like database systems and scientific 
calculations. The current version of nlpsolver does not contain or use large language models
or nontrivial machine learning, except for the components used internally by Stanza.

Installation
------------

The system requires Linux and has been developed using Python 3.8. 
The only external dependencies except Python are:
* The Stanford Stanza NLP package https://stanfordnlp.github.io/stanza/ 
    converting English to a [UD](https://universaldependencies.org/) graph.
* The reasoner binary `gk`, included in the system.
* Data files from the tarball http://logictools.org/data/nlpsolver_data.tar.gz

To run nlpsolver, you need to install Stanza and download and unpack the data files 
from the url above. No other additional packages or special installation is necessary. 

The subfolders `gui` and `amr` contain experimental code in development, and
are not currently used by the nlpsolver pipeline.

Initially we used Stanza versions 1.3.0 and 1.4.1, currently using 1.5.
All of these Stanza versions should be usable for the nlpsolver, although the results of
the semantic parser depend on the Stanza output and may
vary between Stanza versions. The simplest way to install Stanza 
is to run

    pip install stanza
    python -c 'import stanza; stanza.download("en")'

The `gk` reasoner binary is included. It is based on the first order logic
reasoner `gkc` https://github.com/tammet/gkc 
(see the [paper](https://link.springer.com/chapter/10.1007%2F978-3-030-29436-6_32))
and extends the latter with probabilistic and defeasible reasoning mechanisms, see the
[confidences paper](https://link.springer.com/chapter/10.1007/978-3-030-79876-5_29) and the
[default logic reasoning paper](https://link.springer.com/chapter/10.1007/978-3-031-10769-6_18)
along with the demo page https://logictools.org/gk/

The data files tarball is ca 200 megabytes. Download, `gunzip` and `tar -xf` it to same `nlpsolver`
folder: it contains four textual datafiles, altogether ca 600 megabytes. The files
are used by the gk to assist in the semantic parsing process. In case they are missing,
the nlpserver.py setup process will give an error like

    {"error": "Failed to read taxonomy size  "}

About hardware:
* In case your computer has a suitable graphics card, Stanza will run significantly faster.
* Using gk in the pipeline requires at least 3 gigabytes of shared memory.


Running nlpsolver
-----------------

Before running nlpsolver you need to start 

    ./nlpserver.py

The server initializes Stanza, reads relevant data to 3 gigabytes of shared memory for gk
use and starts up a local server (default port 8080) used by the nlpsolver
to call Stanza without the need to re-initialize it for each call. The server will
print `Server ready.` when it is ready for use.

Then call nlpsolver with a natural language text ending with a question, like

    ./nlpsolver.py "Elephants are big. John is an elephant. Who is big?"
    
and/or a filename as an argument, with optional keys:

    basic keys:
        -explain   : give an English explanation/proof of the answer    
        -cache     : store and fetch Stanza and gk input/output to/from the cache 
        -logic     : show logic  
        -usekb     : use background knowledge in a memory kb imported by the server
        -debug     : show the details of the whole process
        -simple    : use a very simplified representation: automatically switches on all the three following keys,
                      which can be also switched on separately:
            -nocontext : use a simplified representation without context (time, situation) when creating logic 
            -noexceptions : use a simplified representation without exceptions (blockers) when creating logic
            -simpleproperties: use simplified properties without strength and type parameters; also turns on -noexceptions
        -nosolve   : convert to logic, show prover json input, but do not run the prover  
        -help      : output this helptext 

    controlling the prover:
        -seconds N : give N seconds for proof search (default 1)
        -prover    : show prover json input/output
        -rawresult : output only the json result from the prover
        -axioms file1.js ... fileN.js   : use these files as axioms instead of the axioms_std.js
        -strategy file.js : use the given json strategy file instead of the default search strategy of the prover
        -nokb      : do not use a shared memory knowledge base (NOT implemented yet)      
        -printlevel N : use N>10 to see more of the search process of the prover (10 is default, try 12)

Concerning the -cache key above: the cache file is the sqlite database nlpcache.db created automatically.
In order to clear the cache, simply delete the file nlpcache.db.

Testing and capabilities
------------------------

Run a large number of regression tests by calling

    ./nlptest.py

The actual test files run are configured at the beginning of the python program.
By default, the following test files are run sequentially:
* `tests_core.py`  : core capabilities test
* `tests_hans.py` : a subset of tests from the [HANS set](https://arxiv.org/abs/1902.01007)
* `tests_allen.py`  : tests created from the [Allen ProofWriter demo](https://proofwriter.apps.allenai.org/)

A few failures in the default regression test are acceptable: they may depend on the time resources
given to the prover, the specifics of Stanza output or inability of the test system to correctly
interpret the answer given.

By default the testing program uses the -cache key explained before.

Look at the test files above to gain insights about the semantic parsing capabilities
of the system.

Knowledge bases
---------------

The default knowledge base used for regression tests is a tiny `axioms_std.js`. 

Large knowledge bases can be used by changing the nlpserver.py initialization line

    axiomfiles=None # "wnet_10k.js cnet_50k.js quasi_50k.js" # set to None to read no axioms

The line above provides three relatively small experimental knowledge bases created from 
WordNet, ConceptNet and Quasimodo, respectively
(see [the paper](https://www.scitepress.org/Link.aspx?doi=10.5220/0011532200003335))


Configuration
-------------

The main configuration parameters are at the beginning of `nlpglobals.py`.
The server configuration parameters are at the beginning of `nlpserver.py`.

Performance
-----------

The system has miserable performance on most well-known natural language inference 
or question answering benchmarks, the majority of which are oriented towards 
machine learning. As an exception, the performance on the anti-machine-
learning question set [HANS](https://arxiv.org/abs/1902.01007) is ca 95%, 
in contrast to the ca 60% performance of LLM systems before the GPT3 family 
(random choice would give 50% performance). The loss of 5% of HANS is due 
to the wrong UD parses chosen by Stanza.

However, the system is able to solve almost all of the demonstration examples 
of the [Allen ProofWriter demo](https://proofwriter.apps.allenai.org/)
and is able to solve inference problems the current LLM systems cannot, like the
following examples:
* ChatGPT answers correctly the question 
    `If an animal likes honey, then it is probably a bear.
    Most bears are big, although young bears are not big. John is an animal who
    likes honey. Mike is a young bear. Who is big?` 
    but fails to answer the modification
    `If a greezer likes foozers, then it is probably
    a drimm. Greezers can eat frozen bread. Most drimms are red, although young
    drimms are not red. John likes bread. John is a nice greezer who likes foozers.
    Mike is a young drimm. Mike can eat a lot. Penguins are birds who cannot
    fly. Who is red?`
* Again, ChatGPT answers correctly the question 
    `The length of the red car is 4 meters. The length
    of the black car is 5 meters. The length of the red car is less than 5 meters?`
    but fails to answer the modification
    `The length of the barner is
    200000000 meters. The length of the red foozer is 312435 meters. The length of
    the black foozer is 512000 meters. The length of the yellow foozer is 1000000
    meters. The length of the red foozer is less than 312546 meters?`

Both these two original questions and their modified versions are answered
correctly by the nlpsolver.

The runtime for the small examples is ca 0.5 seconds
on a Linux laptop with a graphics card usable by Stanza. Of this time, Stanza
UD parsing takes ca 0.17 seconds, UD to logic takes ca 0.04 seconds, and the rest
is spent by the reasoner. For more complex examples the reasoner may spend
unlimited time, i.e. the question is rather how complex questions can be solved
in a preconfigured time window. In case the size of the input problem is relatively
small and a tiny world model suffices for the solution, the correct answer is found
in a range of ca 0.2 to 2 seconds. However, in case the system is given a large knowledge base
with a size of roughly one gigabyte, and the answer actually depends on
the KB, then the search space may explode and the system may fail to find
answer in a reasonable time. Efficiently handling a very large knowledge base
for complex questions is one direction of our current research.

Examples
---------

The simplest way to call:

    ./nlpsolver.py "Most elephants are big. Young elephants are not big. 
          Mike is probably an elephant. John is a young elephant. Who is big?"

results in the output

    Likely Mike.

Adding a key -explain like 

    ./nlpsolver.py "Most elephants are big. Young elephants are not big. 
          Mike is probably an elephant. John is a young elephant. Who is big?"
          -explain

will output an answer with an explanation constructed from the proof found by gk:

    Answer:
    Likely Mike. 

    Explained:

    Likely mike:
    Confidence 76%.
    Sentences used:
    (1) Most elephants are big.
    (2) Mike is probably an elephant.
    (3) Who is big?
    Statements inferred:
    (1) If X is an elephant, then X is big. Confidence 85%. Why: sentence 1.
    (2) Mike is an elephant. Confidence 90%. Why: sentence 2.
    (3) Mike is big. Confidence 76%. Why: statements 1, 2.
    (4) If X is a big Y, then X matches the query. Why: sentence 3.
    (5) Mike matches the query. Confidence 76%. Why: statements 3, 4.
    (6) If X matches the query, then X is an answer. Why: the question.
    (7) Mike is an answer. Confidence 76%. Why: statements 5, 6.


For other options and additional details in the output, see the keys
explained in the "Running nlpsolver" section above.

Finally, adding a key -debug gives the following detailed output, interleaved
by manually inserted comments between *** asterisks ***. 

Notice that gk input and output is in the 
[JSON-LD-LOGIC](https://github.com/tammet/json-ld-logic) format:
see the [paper](https://ieeexplore.ieee.org/abstract/document/9364411)


*** Initial input ***

    answer_question text : Most elephants are big. Young elephants are not big. 
          Mike is probably an elephant. John is a young elephant. Who is big?


*** Textual preprocessing: no changes here. The result below is the same as input. ***

    answer_question prepared text : Most elephants are big. Young elephants are not big. 
          Mike is probably an elephant. John is a young elephant. Who is big?

*** Universal Dependencies structure produced by Stanza (printed in a simplified form). ***

    doc tree:

    sentence 0:
    ============
    root: big [id:4 text:big upos:ADJ xpos:JJ feats:Degree=Pos ner:O]
      nsubj: elephant [id:2 text:elephants upos:NOUN xpos:NNS feats:Number=Plur ner:O]
        amod: most [id:1 text:Most upos:ADJ xpos:JJS feats:Degree=Sup ner:O]
      cop: be [id:3 text:are upos:AUX xpos:VBP feats:Mood=Ind|Number=Plur|Person=3|Tense=Pres|VerbForm=Fin ner:O]
      punct: . [id:5 text:. upos:PUNCT xpos:. ner:O]

    sentence 1:
    ============
    root: big [id:5 text:big upos:ADJ xpos:JJ feats:Degree=Pos ner:O]
      nsubj: elephant [id:2 text:elephants upos:NOUN xpos:NNS feats:Number=Plur ner:O]
        amod: Young [id:1 text:Young upos:ADJ xpos:JJ feats:Degree=Pos ner:O]
      cop: be [id:3 text:are upos:AUX xpos:VBP feats:Mood=Ind|Number=Plur|Person=3|Tense=Pres|VerbForm=Fin ner:O]
      advmod: not [id:4 text:not upos:PART xpos:RB ner:O]
      punct: . [id:6 text:. upos:PUNCT xpos:. ner:O]

    sentence 2:
    ============
    root: elephant [id:5 text:elephant upos:NOUN xpos:NN feats:Number=Sing ner:O]
      nsubj: Mike [id:1 text:Mike upos:PROPN xpos:NNP feats:Number=Sing ner:S-PERSON]
      cop: be [id:2 text:is upos:AUX xpos:VBZ feats:Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin ner:O]
      advmod: probably [id:3 text:probably upos:ADV xpos:RB ner:O]
      det: a [id:4 text:an upos:DET xpos:DT feats:Definite=Ind|PronType=Art ner:O]
      punct: . [id:6 text:. upos:PUNCT xpos:. ner:O]

    sentence 3:
    ============
    root: elephant [id:5 text:elephant upos:NOUN xpos:NN feats:Number=Sing ner:O]
      nsubj: John [id:1 text:John upos:PROPN xpos:NNP feats:Number=Sing ner:S-PERSON]
      cop: be [id:2 text:is upos:AUX xpos:VBZ feats:Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin ner:O]
      det: a [id:3 text:a upos:DET xpos:DT feats:Definite=Ind|PronType=Art ner:O]
      amod: young [id:4 text:young upos:ADJ xpos:JJ feats:Degree=Pos ner:O]
      punct: . [id:6 text:. upos:PUNCT xpos:. ner:O]

    sentence 4:
    ============
    root: big [id:3 text:big upos:ADJ xpos:JJ feats:Degree=Pos ner:O]
      nsubj: who [id:1 text:Who upos:PRON xpos:WP feats:PronType=Int ner:O]
      cop: be [id:2 text:is upos:AUX xpos:VBZ feats:Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin ner:O]
      punct: ? [id:4 text:? upos:PUNCT xpos:. ner:O]

    entities:
      {'text': 'Mike', 'type': 'PERSON', 'start_char': 60, 'end_char': 64}
      {'text': 'John', 'type': 'PERSON', 'start_char': 90, 'end_char': 94}

    final newtext : Most elephants are big.

*** Convert sentence 0 to logic: stepwise ***

    ====== sentence ==========

    root: big [id:4 text:big upos:ADJ xpos:JJ feats:Degree=Pos ner:O]
      nsubj: elephant [id:2 text:elephants upos:NOUN xpos:NNS feats:Number=Plur ner:O]
        amod: most [id:1 text:Most upos:ADJ xpos:JJS feats:Degree=Sup ner:O]
      cop: be [id:3 text:are upos:AUX xpos:VBP feats:Mood=Ind|Number=Plur|Person=3|Tense=Pres|VerbForm=Fin ner:O]
      punct: . [id:5 text:. upos:PUNCT xpos:. ner:O]

    subsentence_logic_tree
    svo [ elephant be big ]

    object_logic_tree
    svo [ elephant be big ]

    property_logic_tree
    svo [ elephant be big ]

    flat_logic_tree
    svo [ elephant be big ]

    flat_props_tree
    svo [ elephant be big ]


    main logic created:

    [forall,[?:S2],[[isa,elephant,?:S2,[$conf,1,False]],=>,[prop,big,?:S2,$generic,$generic,[$conf,0.85,True],[$ctxt,Pres,1]]]]

    === objects detected: === 


*** Convert sentence 1 to logic: stepwise ***

    final newtext : Young elephants are not big.

    ====== sentence ==========

    root: big [id:5 text:big upos:ADJ xpos:JJ feats:Degree=Pos ner:O]
      nsubj: elephant [id:2 text:elephants upos:NOUN xpos:NNS feats:Number=Plur ner:O]
        amod: young [id:1 text:Young upos:ADJ xpos:JJ feats:Degree=Pos ner:O]
      cop: be [id:3 text:are upos:AUX xpos:VBP feats:Mood=Ind|Number=Plur|Person=3|Tense=Pres|VerbForm=Fin ner:O]
      advmod: not [id:4 text:not upos:PART xpos:RB ner:O]
      punct: . [id:6 text:. upos:PUNCT xpos:. ner:O]

    subsentence_logic_tree
    svo [ elephant be big ]

    object_logic_tree
    svo [ elephant be big ]

    property_logic_tree
    svo [ [props,young,elephant] be big ]

    flat_logic_tree
    svo [ [props,young,elephant] be big ]

    flat_props_tree
    svo [ [props,young,elephant] be big ]

    main logic created:

    [forall,[?:S4],[[and,[prop,young,?:S4,$generic,$generic,[$conf,1,False],[$ctxt,Pres,1]],[isa,elephant,?:S4,[$conf,1,False]]],=>,[-prop,big,?:S4,$generic,$generic,[$conf,1,True],[$ctxt,Pres,1]]]]

    === objects detected: === 



*** Convert sentence 2 to logic: stepwise ***

    final newtext : Mike is probably an elephant.

    ====== sentence ==========

    root: elephant [id:5 text:elephant upos:NOUN xpos:NN feats:Number=Sing ner:O]
      nsubj: Mike [id:1 text:Mike upos:PROPN xpos:NNP feats:Number=Sing ner:S-PERSON]
      cop: be [id:2 text:is upos:AUX xpos:VBZ feats:Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin ner:O]
      advmod: probably [id:3 text:probably upos:ADV xpos:RB ner:O]
      det: a [id:4 text:an upos:DET xpos:DT feats:Definite=Ind|PronType=Art ner:O]
      punct: . [id:6 text:. upos:PUNCT xpos:. ner:O]

    subsentence_logic_tree
    svo [ Mike be elephant ]

    object_logic_tree
    svo [ Mike be elephant ]

    property_logic_tree
    svo [ Mike be elephant ]

    flat_logic_tree
    svo [ Mike be elephant ]

    flat_props_tree
    svo [ Mike be elephant ]

    main logic created:

    [isa,elephant,c1_Mike,[$conf,0.9,False]]

    === objects detected: === 

    c1_Mike
      source: Mike (deprel: nsubj, upos: PROPN)
      logic:  isa(elephant,c1_Mike)
      names:  Mike


*** Convert sentence 2 to logic: stepwise ***


    final newtext : John is a young elephant.

    ====== sentence ==========

    root: elephant [id:5 text:elephant upos:NOUN xpos:NN feats:Number=Sing ner:O]
      nsubj: John [id:1 text:John upos:PROPN xpos:NNP feats:Number=Sing ner:S-PERSON]
      cop: be [id:2 text:is upos:AUX xpos:VBZ feats:Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin ner:O]
      det: a [id:3 text:a upos:DET xpos:DT feats:Definite=Ind|PronType=Art ner:O]
      amod: young [id:4 text:young upos:ADJ xpos:JJ feats:Degree=Pos ner:O]
      punct: . [id:6 text:. upos:PUNCT xpos:. ner:O]

    subsentence_logic_tree
    svo [ John be elephant ]

    object_logic_tree
    svo [ John be elephant ]

    property_logic_tree
    svo [ John be [props,young,elephant] ]

    flat_logic_tree
    svo [ John be [props,young,elephant] ]

    flat_props_tree
    svo [ John be [props,young,elephant] ]


    main logic created:

    [and
      [prop,young,c2_John,$generic,$generic,[$conf,1,False],[$ctxt,Pres,1]]
      [isa,elephant,c2_John,[$conf,1,False]]]

    === objects detected: === 

    c1_Mike
      source: Mike (deprel: nsubj, upos: PROPN)
      logic:  isa(elephant,c1_Mike)
      names:  Mike
    c2_John
      source: John (deprel: nsubj, upos: PROPN)
      logic:  prop(young,c2_John,$generic,$generic,$ctxt(Pres,1)) & isa(elephant,c2_John)
      names:  John

*** Convert questionsentence to logic: stepwise ***

    final newtext : Who is big?

    ====== modified question sentence ==========

    original text from question doc : Who is big?


*** Introduce a dummy person name to modify the question for the parser ***

    modified question sentence : Dummyname_1 is big?


*** Parse the modified question sentence and convert to logic ***

    ====== sentence ==========

    root: big [id:3 text:big upos:ADJ xpos:JJ feats:Degree=Pos ner:O]
      nsubj: Dummyname_1 [id:1 text:Dummyname_1 upos:PROPN xpos:NNP feats:Number=Sing ner:O]
      cop: be [id:2 text:is upos:AUX xpos:VBZ feats:Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin ner:O]
      punct: ? [id:4 text:? upos:PUNCT xpos:. ner:O]

    subsentence_logic_tree
    svo [ Dummyname_1 be big ]

    object_logic_tree
    svo [ Dummyname_1 be big ]

    property_logic_tree
    svo [ Dummyname_1 be big ]

    flat_logic_tree
    svo [ Dummyname_1 be big ]

    flat_props_tree
    svo [ Dummyname_1 be big ]


    main logic created:

    [prop,big,c3_Dummyname_1,$generic,$free_variable,[$conf,1,False],[$ctxt,Pres,1]]


*** Here are concrete objects detected in the paragraphs along with their immediately given properties ***


    === objects detected: === 

    c1_Mike
      source: Mike (deprel: nsubj, upos: PROPN)
      logic:  isa(elephant,c1_Mike)
      names:  Mike
    c2_John
      source: John (deprel: nsubj, upos: PROPN)
      logic:  prop(young,c2_John,$generic,$generic,$ctxt(Pres,1)) & isa(elephant,c2_John)
      names:  John
    c3_Dummyname_1
      source: Dummyname_1 (deprel: nsubj, upos: PROPN)
      names:  Dummyname_1


    === all sentences processed ===

*** Logic before simplifications and conversion to normal form ***

    logic before simplification:

      [isa,elephant,some_elephant,[$conf,1]]
      [or,[-isa,elephant,?:X],[isa,object,?:X]]
      [prop,young,some_young_elephant,$generic,$generic,[$ctxt,?:Tense5,1]]
      [isa,elephant,some_young_elephant]
      [isa,elephant,some_elephant,[$conf,1]]
      [or,[-isa,elephant,?:X],[isa,object,?:X]]
      {@name:sent_1,  @logic: [or,[-isa,elephant,?:S2,[$conf,1,False]],[prop,big,?:S2,$generic,$generic,[$conf,0.85,True],[$ctxt,Pres,1]]] }
      {@name:sent_2,  @logic: [or,[-prop,young,?:S4,$generic,$generic,[$conf,1,False],[$ctxt,Pres,1]],[-isa,elephant,?:S4,[$conf,1,False]],[-prop,big,?:S4,$generic,$generic,[$conf,1,True],[$ctxt,Pres,1]]] }
      {@name:sent_3,  @logic: [isa,elephant,c1_Mike,[$conf,0.9,False]] }
      {@name:sent_3,  @logic: [or,[isa,person,c1_Mike],[$block,0,[$not,[isa,person,c1_Mike]]]] }
      {@name:sent_3,  @logic: [isa,object,c1_Mike] }
      {@name:sent_4,  @logic: [and
      [prop,young,c2_John,$generic,$generic,[$conf,1,False],[$ctxt,Pres,1]]
      [isa,elephant,c2_John,[$conf,1,False]]] }
      {@name:sent_4,  @logic: [or,[isa,person,c2_John],[$block,0,[$not,[isa,person,c2_John]]]] }
      {@name:sent_4,  @logic: [isa,object,c2_John] }
      {@name:sent_5,  @logic: [forall,[?:Q1],[[$def0,?:Q1],<=>,[prop,big,?:Q1,$generic,$free_variable,[$ctxt,Pres,?:Fv9]]]] }
      {@name:sent_5,  @question: [$def0,?:Q1] }


*** Clausified form of logic along with confidences and exceptions (blockers) ***

    clauses:

    [
    {@logic: [isa,elephant,some_elephant]},
    {@logic: [or, [-isa,elephant,?:X], [isa,object,?:X]]},
    {@logic: [prop,young,some_young_elephant,$generic,$generic,[$ctxt,?:Tense5,1]]},
    {@logic: [isa,elephant,some_young_elephant]},
    {@logic: [or,
        [-isa,elephant,?:S2],
        [prop,big,?:S2,$generic,$generic,[$ctxt,Pres,1]],
        [$block,[$,elephant,1],[$not,[prop,big,?:S2,$generic,$generic,[$ctxt,Pres,1]]]]],
    @name: sent_1,
    @confidence: 0.85},
    {@logic: [or,
        [-prop,young,?:S4,$generic,$generic,[$ctxt,Pres,1]],
        [-isa,elephant,?:S4],
        [-prop,big,?:S4,$generic,$generic,[$ctxt,Pres,1]],
        [$block,[$,elephant,2],[prop,big,?:S4,$generic,$generic,[$ctxt,Pres,1]]]],
    @name: sent_2},
    {@logic: [or,
        [-prop,young,?:S4,$generic,$generic,[$ctxt,Pres,1]],
        [-isa,elephant,?:S4],
        [-prop,big,?:S4,$generic,$generic,[$ctxt,Pres,1]]],
    @name: sent_2,
    @confidence: 0.3},
    {@logic: [isa,elephant,c1_Mike],
    @name: sent_3,
    @confidence: 0.9},
    {@logic: [or, [isa,person,c1_Mike], [$block,0,[$not,[isa,person,c1_Mike]]]],
    @name: sent_3},
    {@logic: [isa,object,c1_Mike],
    @name: sent_3},
    {@logic: [prop,young,c2_John,$generic,$generic,[$ctxt,Pres,1]],
    @name: sent_4},
    {@logic: [isa,elephant,c2_John],
    @name: sent_4},
    {@logic: [or, [isa,person,c2_John], [$block,0,[$not,[isa,person,c2_John]]]],
    @name: sent_4},
    {@logic: [isa,object,c2_John],
    @name: sent_4},
    {@logic: [or, [-$def0,?:Q1], [prop,big,?:Q1,$generic,?:Ignore10,[$ctxt,Pres,?:Fv9]]],
    @name: sent_5},
    {@logic: [or, [$def0,?:Q1], [-prop,big,?:Q1,$generic,?:Ignore11,[$ctxt,Pres,?:Fv9]]],
    @name: sent_5},
    {@question: [$def0,?:Q1],
    @name: sent_5}
    ]

*** Actual input to the prover ***

    === prover input: === 

    [
    {"@logic": ["isa","elephant","some_elephant"]},
    {"@logic": ["or", ["-isa","elephant","?:X"], ["isa","object","?:X"]]},
    {"@logic": ["prop","young","some_young_elephant","$generic","$generic",["$ctxt","?:Tense5",1]]},
    {"@logic": ["isa","elephant","some_young_elephant"]},
    {"@logic": ["or",
        ["-isa","elephant","?:S2"],
        ["prop","big","?:S2","$generic","$generic",["$ctxt","Pres",1]],
        ["$block",["$","elephant",1],["$not",["prop","big","?:S2","$generic","$generic",["$ctxt","Pres",1]]]]],
    "@name": "sent_1",
    "@confidence": 0.85},
    {"@logic": ["or",
        ["-prop","young","?:S4","$generic","$generic",["$ctxt","Pres",1]],
        ["-isa","elephant","?:S4"],
        ["-prop","big","?:S4","$generic","$generic",["$ctxt","Pres",1]],
        ["$block",["$","elephant",2],["prop","big","?:S4","$generic","$generic",["$ctxt","Pres",1]]]],
    "@name": "sent_2"},
    {"@logic": ["or",
        ["-prop","young","?:S4","$generic","$generic",["$ctxt","Pres",1]],
        ["-isa","elephant","?:S4"],
        ["-prop","big","?:S4","$generic","$generic",["$ctxt","Pres",1]]],
    "@name": "sent_2",
    "@confidence": 0.3},
    {"@logic": ["isa","elephant","c1_Mike"],
    "@name": "sent_3",
    "@confidence": 0.9},
    {"@logic": ["or", ["isa","person","c1_Mike"], ["$block",0,["$not",["isa","person","c1_Mike"]]]],
    "@name": "sent_3"},
    {"@logic": ["isa","object","c1_Mike"],
    "@name": "sent_3"},
    {"@logic": ["prop","young","c2_John","$generic","$generic",["$ctxt","Pres",1]],
    "@name": "sent_4"},
    {"@logic": ["isa","elephant","c2_John"],
    "@name": "sent_4"},
    {"@logic": ["or", ["isa","person","c2_John"], ["$block",0,["$not",["isa","person","c2_John"]]]],
    "@name": "sent_4"},
    {"@logic": ["isa","object","c2_John"],
    "@name": "sent_4"},
    {"@logic": ["or", ["-$def0","?:Q1"], ["prop","big","?:Q1","$generic","?:Ignore10",["$ctxt","Pres","?:Fv9"]]],
    "@name": "sent_5"},
    {"@logic": ["or", ["$def0","?:Q1"], ["-prop","big","?:Q1","$generic","?:Ignore11",["$ctxt","Pres","?:Fv9"]]],
    "@name": "sent_5"},
    {"@question": ["$def0","?:Q1"],
    "@name": "sent_5"}
    ]

    === prover params: === 

    ./gk axioms_std.js -seconds 1 /tmp/tmp2wi_jzzx -defaults -confidence 0.1 -keepconfidence 0.1

*** Actual output of the prover: finds two answers: Mike and an arbitrary generic elephant ***

*** Importantly, John is not an answer, since the proof for John is blocked by the knowledge that John is a young elephant *******

    === prover output: === 

    {"result": "answer found",

    "answers": [
    {
    "answer": [["$ans","some_elephant"]],
    "blockers": [["$block",["$","elephant",1],["$not",["prop","big","some_elephant","$generic","$generic",["$ctxt","Pres",1]]]]],
    "confidence": 0.85,
    "positive proof":
    [
    [1, ["in", "sent_1", "axiom", 0.85], [["$block",["$","elephant",1],["$not",["prop","big","?:X","$generic","$generic",["$ctxt","Pres",1]]]], ["prop","big","?:X","$generic","$generic",["$ctxt","Pres",1]], ["-isa","elephant","?:X"]]],
    [2, ["in", "frm_1", "axiom", 1], [["isa","elephant","some_elephant"]]],
    [3, ["mp", [1,2], 2, "fromaxiom", 0.85], [["$block",["$","elephant",1],["$not",["prop","big","some_elephant","$generic","$generic",["$ctxt","Pres",1]]]], ["prop","big","some_elephant","$generic","$generic",["$ctxt","Pres",1]]]],
    [4, ["in", "sent_5", "axiom", 1], [["-prop","big","?:X","$generic","?:Y",["$ctxt","Pres","?:Z"]], ["$def0","?:X"]]],
    [5, ["mp", [3,1], 4, "fromaxiom", 0.85], [["$block",["$","elephant",1],["$not",["prop","big","some_elephant","$generic","$generic",["$ctxt","Pres",1]]]], ["$def0","some_elephant"]]],
    [6, ["in", "sent_5", "goal", 1], [["-$def0","?:X"], ["$ans","?:X"]]],
    [7, ["mp", [5,1], 6, "fromgoal", 0.85], [["$block",["$","elephant",1],["$not",["prop","big","some_elephant","$generic","$generic",["$ctxt","Pres",1]]]], ["$ans","some_elephant"]]]
    ]},
    {
    "answer": [["$ans","c1_Mike"]],
    "blockers": [["$block",["$","elephant",1],["$not",["prop","big","c1_Mike","$generic","$generic",["$ctxt","Pres",1]]]]],
    "confidence": 0.765,
    "positive proof":
    [
    [1, ["in", "sent_1", "axiom", 0.85], [["$block",["$","elephant",1],["$not",["prop","big","?:X","$generic","$generic",["$ctxt","Pres",1]]]], ["prop","big","?:X","$generic","$generic",["$ctxt","Pres",1]], ["-isa","elephant","?:X"]]],
    [2, ["in", "sent_3", "axiom", 0.9], [["isa","elephant","c1_Mike"]]],
    [3, ["mp", [1,2], 2, "fromaxiom", 0.765], [["$block",["$","elephant",1],["$not",["prop","big","c1_Mike","$generic","$generic",["$ctxt","Pres",1]]]], ["prop","big","c1_Mike","$generic","$generic",["$ctxt","Pres",1]]]],
    [4, ["in", "sent_5", "axiom", 1], [["-prop","big","?:X","$generic","?:Y",["$ctxt","Pres","?:Z"]], ["$def0","?:X"]]],
    [5, ["mp", [3,1], 4, "fromaxiom", 0.765], [["$block",["$","elephant",1],["$not",["prop","big","c1_Mike","$generic","$generic",["$ctxt","Pres",1]]]], ["$def0","c1_Mike"]]],
    [6, ["in", "sent_5", "goal", 1], [["-$def0","?:X"], ["$ans","?:X"]]],
    [7, ["mp", [5,1], 6, "fromgoal", 0.765], [["$block",["$","elephant",1],["$not",["prop","big","c1_Mike","$generic","$generic",["$ctxt","Pres",1]]]], ["$ans","c1_Mike"]]]
    ]}
    ]}


    === end of prover output === 

*** Final answer and an explanation: the generic elephant answer is thrown away, since we already have a concrete elephant found ***

    Answer:
    Likely Mike. 

    Explained:

*** The explanation is constructed from the proof above ****

    Likely mike:
    Confidence 76%.
    Sentences used:
    (1) Most elephants are big.
    (2) Mike is probably an elephant.
    (3) Who is big?
    Statements inferred:
    (1) If X is an elephant, then X is big. Confidence 85%. Why: sentence 1.
    (2) Mike is an elephant. Confidence 90%. Why: sentence 2.
    (3) Mike is big. Confidence 76%. Why: statements 1, 2.
    (4) If X is a big Y, then X matches the query. Why: sentence 3.
    (5) Mike matches the query. Confidence 76%. Why: statements 3, 4.
    (6) If X matches the query, then X is an answer. Why: the question.
    (7) Mike is an answer. Confidence 76%. Why: statements 5, 6.






