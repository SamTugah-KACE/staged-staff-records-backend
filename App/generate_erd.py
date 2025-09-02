

from sqlalchemy.orm import class_mapper
from graphviz import Digraph
from database.db_session import Base
from Models.Tenants.organization import *
from Models.Tenants.role import Role
from Models.models import *
from sqlalchemy.orm import configure_mappers




def generate_erd(output_file="erd_diagram"):
    """
    Generates an ERD diagram for all models registered with SQLAlchemy's Base.
    """

    configure_mappers()
    metadata = Base.metadata
    graph = Digraph(format="png", graph_attr={"rankdir": "LR"}, node_attr={"shape": "box"})

    # Add tables and their columns
    for table in metadata.tables.values():
        label = f"<<TABLE BORDER='0' CELLBORDER='1' CELLSPACING='0'><TR><TD><B>{table.name}</B></TD></TR>"
        for column in table.columns:
            label += f"<TR><TD ALIGN='LEFT'>{column.name} ({column.type})</TD></TR>"
        label += "</TABLE>>"
        graph.node(table.name, label=label, shape="plaintext")

    # Add relationships
    for cls_name, cls in Base.registry._class_registry.items():  # Use _class_registry to access mapped classes
        if isinstance(cls, type) and hasattr(cls, "__table__"):
            mapper = class_mapper(cls)
            for relationship in mapper.relationships:
                graph.edge(
                    mapper.local_table.name,
                    relationship.target.name,
                    label=relationship.key,
                    arrowhead="normal",
                )

    # Render diagram
    graph.render(output_file, cleanup=True)
    print(f"ERD generated: {output_file}.png")


if __name__ == "__main__":
    generate_erd()




