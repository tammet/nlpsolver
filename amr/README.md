# AMR parsing for nlpsolver

`nlpgui` provides browser environment for running the nlpsolver.

## Installation and running

### Installing Python dependencies
Install the required Python dependencies: `pip install -r requirements.txt`. 

### Installing AMR parsing model

Install the model for AMR parsing:
1. Go to `https://github.com/bjascob/amrlib-models`
2. Choose a sentence-to-graph model for parsing. We have been using 
   `parse_t5 0.2.0` (for single sentence parsing) and `parse_xfm_bart_base` 
   (for multi-sentence parsing)
3. Download the selected model to your local drive. 
4. Unpack the model and place the files under `models/model_stog` directory. 
5. Verify the location of model files: the directory `models/model_stog` 
   should contain four files: `amrlib_meta.json`, `config.json`, 
   `pytorch_model.bin` and `training_args.bin`

### Updating Propbank
By default, NLTK uses Propbank 1.0 corpus. Our system uses Propbank 3.4.
NLTK corpora are stored at `~/nltk_data/corpora` directory. 

To upgrade the Propbank to the latest version (currently 3.4), do the following:
```
cd ~/nltk_data/corpora
git clone https://github.com/propbank/propbank-frames.git propbank-3.4
```


### Running the server

1. Start the server by running `./amrserver.py`. You can change the default 
port by changing the `amr_server_port` variable in `amrconfig.py` file. 
2. Make GET request to server, e.g `wget http://localhost:9000/?text=John is a 
   man.`. A JSON response is returned