# AMR parsing for nlpsolver

`nlpgui` provides browser environment for running the nlpsolver.

## Installation and running

1. Install the requirements `pip install -r requirements.txt`
2. Download the model from `https://github.com/bjascob/amrlib-models`. Unpack the model files and place them under `models/model_stog` directory. We have been using `parse_t5` and `parse_xfm_bart_base` for our experiments.
3. Start the server by running `./amrserver.py`
4. Make GET request to server, e.g `http://localhost:9000/?text=John is a man.`. A JSON response is returned