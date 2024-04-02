# uniprot

This library provides classes to make an SQLAlchemy database for uniprot data and import it into a neo4j graph.

## Imports

Only two classes are needed for the full functionality of the package:

```python
from uniprot.manager import Database
from uniprot.import_neo4j import Neo4j_Importer
````
## Usage

```python
url = "sqlite:///" + "../test_uniprot.db"
db = Database(url)
db.recreate_database()
db.import_all("../tests/data/test_data.tsv")
NeoImp = Neo4j_Importer()
NeoImp.create_ttl(db, os.path.join(DATA_FOLDER, "uniprot.ttl"))
NeoImp.drop_graph()
NeoImp.import_to_neo4j("data/uniprot.ttl")
````
This example code shows the usage of the package. 
The tsv file must contain data downloaded from [Uniprot](https://www.uniprot.org). The Database class will generate a .db file where all the data from the tsv-file is stored. 

The structure of the tables of the database can be viewed [here]('../src/uniprot/models.py').

The Neo4j_Importer class generates a ttl file for the data in the database, which can then be imported into neo4j to view the graph.
