from rdflib import Graph, URIRef, Literal, Namespace, RDF, XSD, RDFS
import pandas as pd
from rdflib_neo4j import Neo4jStore, HANDLE_VOCAB_URI_STRATEGY, Neo4jStoreConfig
from neo4j import GraphDatabase
from uniprot.manager import Database
from uniprot.models import (
    UniProt,
    GeneName,
    Go,
    Brenda,
    association_table_uniprot_brenda,
    association_table_uniprot_go,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


class Neo4j_Importer:
    def __init__(
        self,
        uri: str = "neo4j://localhost:7687",
        user: str = "neo4j",
        password: str = "neo4j_passwd",
    ):
        """
        Initializes Neo4j_Importer object.

        Args:
            uri (str, optional): Port of neo4j. Defaults to "neo4j://localhost:7687".
            user (str, optional): User name for neo4j login. Defaults to "neo4j".
            password (str, optional): Password for neo4j login. Defaults to "neo4j_passwd".
        """
        self.__uri = uri
        self.__user = user
        self.__pwd = password

    def drop_graph(self):
        """
        Drop 50000 existing nodes in the graph.
        Might have to run multiple times if graph was bigger.
        """
        if True:
            driver = GraphDatabase.driver(self.__uri, auth=(self.__user, self.__pwd))
            with driver.session() as session:
                cypher = "MATCH (n) WITH n LIMIT 50000 DETACH DELETE n"
                session.run(cypher)
                cypher = "MATCH (n) DELETE n"
                session.run(cypher)
                cypher = "DROP CONSTRAINT n10s_unique_uri IF EXISTS"
                session.run(cypher)
                cypher = "CREATE CONSTRAINT n10s_unique_uri IF NOT EXISTS  FOR (r:Resource) REQUIRE r.uri IS UNIQUE"
                session.run(cypher)

    def import_to_neo4j(self, ttl_file_path: str):
        """
        Import all data from a ttl file into neo4j.
        """
        config = Neo4jStoreConfig(
            auth_data={
                "uri": self.__uri,
                "database": "neo4j",
                "user": self.__user,
                "pwd": self.__pwd,
            },
            custom_prefixes={},
            handle_vocab_uri_strategy=HANDLE_VOCAB_URI_STRATEGY.IGNORE,
            batching=True,
        )

        neo4j_db = Graph(store=Neo4jStore(config=config))
        # Calling the parse method will implictly open the store
        neo4j_db.parse(ttl_file_path, format="ttl")
        neo4j_db.close(True)

    def create_ttl(self, database: Database, output_path: str):
        db: Database = database
        graph = Graph()
        up_ns = Namespace("http://purl.uniprot.org/uniprot/")
        own_ns_node_type = Namespace("https://plab2.bit.uni-bonn.de/node#")
        own_ns_rel_type = Namespace("https://plab2.bit.uni-bonn.de/relation#")
        brenda = Namespace("https://www.brenda-enzymes.org/enzyme.php?ecno=")
        organism_ns = Namespace(
            "https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id="
        )
        gene_name_ns = Namespace("https://www.biodb.uni-bonn.de/gene_name/")
        go_ns = Namespace("https://www.ebi.ac.uk/QuickGO/term/")

        graph.bind("uniprot", up_ns)
        graph.bind("node", own_ns_node_type)
        graph.bind("relation", own_ns_rel_type)
        graph.bind("xs", XSD)
        graph.bind("brenda", brenda)
        graph.bind("organism", organism_ns)
        graph.bind("gene_name", gene_name_ns)
        graph.bind("go", go_ns)

        # Construct a select statement that returns all entries in the uniprot table
        session = Session(db.engine)
        uniprot_entries = session.query(UniProt).all()

        for uniprot in uniprot_entries:
            subject: URIRef = up_ns[uniprot.entry]

            graph.add((subject, RDF.type, own_ns_node_type["Protein"]))
            graph.add(
                (
                    subject,
                    own_ns_rel_type["entry_name"],
                    Literal(uniprot.entry, datatype=XSD.string),
                )
            )
            # add brenda ids
            self.add_brenda_ids(
                graph,
                own_ns_node_type,
                own_ns_rel_type,
                brenda,
                session,
                uniprot.entry,
                subject,
            )

            # add GO terms
            self.add_go_terms(
                graph,
                own_ns_node_type,
                own_ns_rel_type,
                session,
                uniprot.entry,
                subject,
                go_ns=go_ns,
            )

            # add Gene names
            self.add_gene_names(
                graph,
                own_ns_node_type,
                own_ns_rel_type,
                session,
                uniprot.id,
                subject,
                gene_name_ns,
            )
            # add organism
            self.add_organism(
                graph, own_ns_rel_type, organism_ns, uniprot, subject, own_ns_node_type
            )

            self.add_protein_name(graph, own_ns_rel_type, uniprot, subject)
        graph.serialize(output_path, format="turtle")

    def add_organism(
        self,
        graph: Graph,
        own_ns_rel_type: Namespace,
        organism_ns: Namespace,
        uniprot: UniProt,
        subject: URIRef,
        own_ns_node_type,
    ):
        if not pd.isna(uniprot.organism):
            organism_uri = organism_ns[str(uniprot.organism_id)]
            graph.add(
                (
                    subject,
                    own_ns_rel_type["xfref_organsim"],
                    organism_uri,
                )
            )
            graph.add(
                (
                    organism_uri,
                    RDF.type,
                    own_ns_node_type["Organism"],
                )
            )
            graph.add(
                (
                    organism_uri,
                    own_ns_rel_type["Scientific_Name"],
                    Literal(uniprot.organism, datatype=XSD.string),
                )
            )
            graph.add(
                (
                    organism_uri,
                    own_ns_rel_type["Organism_id"],
                    Literal(uniprot.organism_id, datatype=XSD.string),
                )
            )

    def add_protein_name(
        self,
        graph: Graph,
        own_ns_rel_type: Namespace,
        uniprot: UniProt,
        subject: URIRef,
    ):
        # add protein name
        if not pd.isna(uniprot.protein_name):
            predicate = own_ns_rel_type["protein_name"]
            graph.add(
                (
                    subject,
                    predicate,
                    Literal(uniprot.protein_name, datatype=XSD.string),
                )
            )

    def add_gene_names(
        self,
        graph: Graph,
        own_ns_node_type: Namespace,
        own_ns_rel_type: Namespace,
        session: Session,
        uniprot_id: int,
        subject: URIRef,
        gene_name_ns: Namespace,
    ):
        gene_names = session.query(GeneName).filter_by(uniprot_id=uniprot_id).all()
        for gene_name in gene_names:
            gene_name = gene_name.gene
            gene_uri = gene_name_ns[gene_name]
            graph.add(
                (
                    subject,
                    own_ns_rel_type["gene_id"],
                    gene_uri,
                )
            )
            graph.add(
                (
                    gene_uri,
                    RDF.type,
                    own_ns_node_type["Gene_Name"],
                )
            )
            graph.add(
                (
                    gene_uri,
                    own_ns_rel_type["gene_name"],
                    Literal(gene_name, datatype=XSD.string),
                )
            )

    def add_go_terms(
        self,
        graph: Graph,
        own_ns_node_type: Namespace,
        own_ns_rel_type: Namespace,
        session: Session,
        uniprot_id: str,
        subject: URIRef,
        go_ns: Namespace,
    ):
        go_stmt = (
            select(Go)
            .join(
                association_table_uniprot_go,
                Go.id == association_table_uniprot_go.c.go_id,
            )
            .join(UniProt, association_table_uniprot_go.c.uniprot_id == UniProt.id)
            .filter(UniProt.entry == uniprot_id)
        )
        go_result = session.execute(go_stmt)
        for go_row in go_result:
            go_id = go_row[0].goid
            go_uri = go_ns[go_id]

            graph.add(
                (
                    subject,
                    own_ns_rel_type["go_id"],
                    go_uri,
                )
            )
            graph.add((go_uri, RDF.type, own_ns_node_type["GO_term"]))
            graph.add(
                (go_uri, own_ns_rel_type["Go_id"], Literal(go_id, datatype=XSD.string))
            )

    def add_brenda_ids(
        self,
        graph: Graph,
        own_ns_node_type: Namespace,
        own_ns_rel_type: Namespace,
        brenda_ns: Namespace,
        session: Session,
        uniprot_id: str,
        subject: URIRef,
    ):
        brenda_stmt = (
            select(Brenda)
            .join(
                association_table_uniprot_brenda,
                Brenda.id == association_table_uniprot_brenda.c.brenda_id,
            )
            .join(UniProt, association_table_uniprot_brenda.c.uniprot_id == UniProt.id)
            .filter(UniProt.entry == uniprot_id)
        )
        brenda_result = session.execute(brenda_stmt)  # currently is none
        for brenda_row in brenda_result:
            brenda_ec = brenda_row[0].brenda_id
            brenda_uri = brenda_ns[brenda_ec]
            graph.add(
                (
                    subject,
                    own_ns_rel_type["xref_brenda"],
                    brenda_uri,
                )
            )
            graph.add(
                (
                    brenda_uri,
                    RDF.type,
                    own_ns_node_type["EC_number"],
                )
            )
            graph.add(
                (
                    subject,
                    RDF.type,
                    own_ns_node_type["Enzyme"],
                )
            )
            graph.add(
                (
                    brenda_uri,
                    own_ns_rel_type["ec_number"],
                    Literal(brenda_ec, datatype=XSD.string),
                )
            )
