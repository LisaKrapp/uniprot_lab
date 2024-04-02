from uniprot.manager import Database
from uniprot.models import (
    UniProt,
    Go,
    Brenda,
    association_table_uniprot_brenda,
    association_table_uniprot_go,
)
from uniprot.import_neo4j import Neo4j_Importer
from sqlalchemy import MetaData, select, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from typing import List
from neo4j import GraphDatabase, Record, Result
import pytest
import os


PATH_TO_DATA = os.path.join("tests", "data", "test_data.tsv")
url = "sqlite:///" + "test_uniprot.db"


class TestUniprot:
    def setup_method(self, method):
        """Setup method to provide always a database instance as self.db."""
        db = Database(url)
        self.db = db
        self.db.recreate_database()
        self.db.import_all(PATH_TO_DATA)
        self.neo4j_importer = Neo4j_Importer()
        self.ttl_path = os.path.join("tests", "data", "uniprot_test.ttl")

    def test_has_connection(self):
        """Test if the database has a connection to the engine."""
        try:
            with self.db.engine.connect():
                # If connection succeeds, assert that the connection is valid
                assert True, "Connection to the database is successful"
        except OperationalError as e:
            # If connection fails, raise an assertion error with the error message
            pytest.fail(f"Failed to connect to the database: {e}")

    def test_read_data(self):
        """
        Test if the test data given to the DB contains two rows.
        """
        assert len(self.db.dataframe) == 3

    def test_what_tables(self):
        """
        Test if the correct tables got created.
        """
        metadata = MetaData()
        metadata.reflect(bind=self.db.engine)
        table_names = metadata.tables.keys()
        assert table_names == {
            "uniprot",
            "go",
            "brenda",
            "gene_name",
            "uniprot_brenda_association",
            "uniprot_go_association",
        }

    def test_drop_all(self):
        """
        Test if the drop_database method drops all tables.
        """
        self.db.drop_database()
        metadata = MetaData()
        metadata.reflect(bind=self.db.engine)
        table_names = metadata.tables.keys()
        assert not table_names

    def test_protein_names(self):
        """
        Test if the protein names got correctly imported.
        """
        self.db.recreate_database()
        self.db.import_all(PATH_TO_DATA)
        session = Session(self.db.engine)
        stmt = select(UniProt.entry)
        entries = session.scalars(stmt)
        entry_values: List[str] = [entry for entry in entries]
        expected_entries = ["A0A0E3T3B5", "A0A0E3T552", "test_entry"]
        assert entry_values == expected_entries

    def test_first_go_terms(self):
        """
        Test if the GO ids of the first protein are correctly imported.
        """
        session = Session(self.db.engine)
        stmt = stmt = (
            select(Go.goid)
            .join(
                association_table_uniprot_go,
                Go.id == association_table_uniprot_go.c.go_id,
            )
            .join(UniProt, association_table_uniprot_go.c.uniprot_id == UniProt.id)
            .where(UniProt.entry == "A0A0E3T3B5")
        )
        entries = session.scalars(stmt)
        entry_values = {entry for entry in entries}
        expected_entries = {
            "GO:0005777",
            "GO:0019145",
            "GO:0019285",
            "GO:0033737",
            "GO:0046872",
            "GO:0110095",
        }
        assert entry_values == expected_entries

    def test_no_go_terms_for_third_row(self):
        """
        Test if there is no entry for GO ids for the third protein.
        """
        session = Session(self.db.engine)
        stmt = (
            select(UniProt.entry)
            .join(
                Go, UniProt.gos, isouter=True
            )  # Use outer join to include UniProt instances even if they don't have associated Go instances
            .group_by(
                UniProt.id
            )  # Group by UniProt.id to avoid duplicates in case of multiple Go instances per UniProt entry
            .having(
                func.count(Go.id) > 0
            )  # Filter to select UniProt entries with at least one associated Go instance
        )
        entries = session.scalars(stmt)
        entry_values = [entry for entry in entries]

        assert "test_entry" not in entry_values

    def test_brenda_ids(self):
        """
        Test if the correct BRENDA entries are imported.
        """
        session = Session(self.db.engine)
        stmt = (
            select(Brenda.brenda_id)
            .join(
                association_table_uniprot_brenda,
                Brenda.id == association_table_uniprot_brenda.c.brenda_id,
            )
            .join(UniProt, association_table_uniprot_brenda.c.uniprot_id == UniProt.id)
            .filter(or_(UniProt.entry == "A0A0E3T3B5", UniProt.entry == "A0A0E3T552"))
        )
        entries = session.execute(stmt)

        # Extract the values from the result
        entry_values = {entry[0] for entry in entries}

        # Define the expected entries
        expected_entries = {"1.2.1.19", "1.1.1.1", "EC.1"}

        # Perform the assertion
        assert entry_values == expected_entries

    def test_create_ttl(self):
        """
        Test if ttl file gets gets created.
        """
        self.neo4j_importer.create_ttl(self.db, self.ttl_path)
        assert os.path.exists(self.ttl_path)

    def test_import_neo4j(self):
        """
        Test if nodes get imported into neo4j.
        """
        self.neo4j_importer.drop_graph()
        self.neo4j_importer.import_to_neo4j(self.ttl_path)
        with GraphDatabase.driver(
            "neo4j://localhost:7687", auth=("neo4j", "neo4j_passwd")
        ) as driver:
            with driver.session() as session:
                # Write a Cypher query to count the number of nodes of interest
                cypher_query = "MATCH (n) RETURN count(n) AS nodeCount"
                # Execute the query
                result: Record | None = session.run(cypher_query).single()

                # Retrieve the node count from the result
                if result:
                    node_count = result["nodeCount"]

                # Assert that the node count is greater than 0, indicating that nodes were imported
                assert node_count == 18

    def test_delete_ttl(self):
        """
        Test to delete ttl file to start new each testing round.
        """
        os.remove(self.ttl_path)
        assert os.path.exists(self.ttl_path) == False
