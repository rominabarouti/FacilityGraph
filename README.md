# Interactive facility graph

This project is designed to generate and display an interactive graph representation of facility spaces from an IFC 4x3 model.  
It builds a spatial adjacency and containment graph from IFC data and renders it directly in the browser using a 3D force-directed graph.

The graph data is generated using a Python pipeline and visualized as a web-based interactive viewer.

The visualization is based on the 3D Force Graph web representation by  
Copyright (c) 2017 Vasco Asturiano.

---

# Project Structure

Interactive facility graph
├── data
│ ├── facility.graphml # Generated graph data
│ └── facility.png # Optional static graph image
├── generate_graph.py # IFC → GraphML generator
├── index.html # Interactive 3D graph viewer
├── README.md # Project documentation
└── requirements.txt # Python dependencies

# Usage

### Generate graph data
1. Set the path to your IFC file in `build_graphml.py`
2. Run the script:
   ```bash
   python build_graphml.py
   ```
3. This generates a GraphML file in the data/ directory.

### View the interactive graph

Start a local web server:

```bash
python -m http.server
```

Open your browser at:

```bash
http://localhost:8000/graph.html
```

The interactive graph will be displayed on the main page.
## Contributing

Feel free to submit issues or pull requests if you have suggestions, improvements, or extensions for the project.  

## Licence
This project is licensed under the MIT License. 
   
