from typing import List
from typing import Optional
from sqlalchemy import Table, Column, ForeignKey
from sqlalchemy import String, Integer
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship


class Base(DeclarativeBase):
    pass


association_table_uniprot_brenda = Table(
    "uniprot_brenda_association",
    Base.metadata,
    Column("uniprot_id", Integer, ForeignKey("uniprot.id")),
    Column("brenda_id", Integer, ForeignKey("brenda.id")),
)

association_table_uniprot_go = Table(
    "uniprot_go_association",
    Base.metadata,
    Column("uniprot_id", Integer, ForeignKey("uniprot.id")),
    Column("go_id", Integer, ForeignKey("go.id")),
)


class UniProt(Base):
    """
    Main table of the uniprot database.

    Args:
        Base (_type_): Base class from SQLalchemy

    """

    __tablename__ = "uniprot"
    id: Mapped[int] = mapped_column(primary_key=True)
    entry: Mapped[str]
    gene_names: Mapped[List["GeneName"]] = relationship(
        back_populates="uniprot", cascade="all, delete-orphan"
    )
    organism: Mapped[str]
    organism_id: Mapped[int]
    protein_name: Mapped[str]
    gos: Mapped[List["Go"]] = relationship(
        "Go",
        secondary=association_table_uniprot_go,
        back_populates="uniprot_id",
    )
    brendas: Mapped[List["Brenda"]] = relationship(
        "Brenda",
        secondary=association_table_uniprot_brenda,
        back_populates="uniprot_id",
    )

    def __repr__(self) -> str:
        return f"UniProt(id={self.id!r}, entry={self.entry!r})"


class GeneName(Base):
    """
    Table that contains data for the gene names.

    Args:
        Base (_type_): Base class from SQLAlchemy

    """

    __tablename__ = "gene_name"
    id: Mapped[int] = mapped_column(primary_key=True)
    gene: Mapped[str]
    uniprot_id: Mapped[int] = mapped_column(ForeignKey("uniprot.id"))
    uniprot: Mapped[UniProt] = relationship(back_populates="gene_names")

    def __repr__(self) -> str:
        return f"Go(id={self.id!r}, goid={self.gene!r})"


class Go(Base):
    """
    Table that contains ids for all go ids.
    Connected with the association_table_uniprot_go.

    Args:
        Base (_type_): Base clas from SQLAlchemy


    """

    __tablename__ = "go"
    id: Mapped[int] = mapped_column(primary_key=True)
    goid: Mapped[str]
    uniprot_id = relationship(
        "UniProt", secondary=association_table_uniprot_go, back_populates="gos"
    )

    def __repr__(self) -> str:
        return f"Go(id={self.id!r}, goid={self.goid!r})"


class Brenda(Base):
    """
    Table that contains ids for all brenda ids.
    Connected with the association_table_uniprot_brenda.

    Args:
        Base (_type_): Base clas from SQLAlchemy


    """

    __tablename__ = "brenda"
    id: Mapped[int] = mapped_column(primary_key=True)
    brenda_id: Mapped[str]
    uniprot_id = relationship(
        "UniProt", secondary=association_table_uniprot_brenda, back_populates="brendas"
    )

    def __repr__(self) -> str:
        return f"Go(id={self.id!r}, goid={self.brenda_id!r})"
