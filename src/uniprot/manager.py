from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from uniprot.models import Base, UniProt, Go, Brenda, GeneName
import pandas as pd
import numpy as np


class Database:
    def __init__(self, url: str, echo=False):
        """
        Initializes a Database instance.

        Args:
            url (str): url of the database engine
            echo (bool, optional): echo prints SQL methods. Defaults to False.
        """
        self.engine: Engine = create_engine(url=url, echo=echo)

    def create_database(self):
        """Create all tables in the database."""
        Base.metadata.create_all(self.engine)

    def drop_database(self):
        """Drop all tables in the database."""
        Base.metadata.drop_all(self.engine)

    def recreate_database(self):
        """Recreate all tables in the database."""
        self.drop_database()
        self.create_database()

    def read_tsv_file(self, path: str):
        """
        Read dataframe in tsv file, select only wanted columns,
        rename index to id and store as self.dataframe.

        Args:
            path (str): Path to tsv file that contains uniprot data
        """
        self.dataframe = pd.read_csv(
            path,
            sep="\t",
            usecols=[
                "Entry",
                "Protein names",
                "Organism",
                "Organism (ID)",
                "Gene Ontology IDs",
                "BRENDA",
                "Gene Names",
            ],
            low_memory=False,
        )
        self.dataframe["gene_names"] = self.dataframe["Gene Names"].str.split(" ")
        self.dataframe["protein_names"] = self.dataframe["Protein names"]
        self.dataframe["goid"] = self.dataframe["Gene Ontology IDs"].str.split("; ")

        # Define a regular expression pattern to extract the scientific name
        pattern = r"(\b[a-zA-Z]+\s+[a-zA-Z]+)"
        # Extract the scientific name using the pattern and create a new column
        self.dataframe["Scientific_Name"] = self.dataframe["Organism"].str.extract(
            pattern
        )
        self.dataframe["organism_id"] = self.dataframe["Organism (ID)"]
        self.dataframe["brenda_id"] = (
            self.dataframe["BRENDA"]
            .str.rstrip(
                ";"
            )  # get rid of the last semicolon to the right, because it has no " "
            .str.split("; ")
        )
        self.dataframe.index.rename("id", inplace=True)

    def import_all(self, path: str):
        """
        Import data for all tables into the database from tsv file.

        Args:
            path (str): Path to tsv file containing uniprot data.
        """
        self.read_tsv_file(path)

        Session = sessionmaker(bind=self.engine)
        with Session() as session:

            for _, data in self.dataframe.iterrows():
                gene_names = (
                    [GeneName(gene=x) for x in data.gene_names]
                    if isinstance(data.gene_names, list)
                    else []
                )

                goids = []
                for goid in set(data.goid) if isinstance(data.goid, list) else []:
                    go = session.query(Go).filter_by(goid=goid).first()
                    if go:
                        goids.append(go)
                    else:
                        go = Go(goid=goid)
                        goids.append(go)
                        session.add(go)

                brenda_ids = []
                for brenda_id in (
                    set(data.brenda_id) if isinstance(data.brenda_id, list) else []
                ):
                    brenda = (
                        session.query(Brenda).filter_by(brenda_id=brenda_id).first()
                    )
                    if brenda:
                        brenda_ids.append(brenda)
                    else:
                        brenda = Brenda(brenda_id=brenda_id)
                        brenda_ids.append(brenda)
                        session.add(brenda)

                uniprot = UniProt(
                    entry=data.Entry,
                    organism=data.Scientific_Name,
                    organism_id=data.organism_id,
                    protein_name=data.protein_names,
                    gos=goids,
                    brendas=brenda_ids,
                    gene_names=gene_names,
                )
                session.add(uniprot)
            session.commit()
