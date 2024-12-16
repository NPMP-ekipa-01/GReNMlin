# Application Info
APP_NAME = "GReNMlin"
APP_VERSION = "0.1.0"
APP_DESCRIPTION = "Gene Regulatory Network Modeling Interface"
APP_LONG_DESCRIPTION = (
    "A tool for constructing and simulating models of gene regulatory networks."
)
GITHUB_URL = "https://github.com/mmoskon/GReNMlin"
ICON_FILENAME = "logo.png"

################################################################################

import json
import os
import sys
from enum import Enum

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Needs to be imported after Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

import simulator
from grn import GRN


class NetworkNode(QGraphicsEllipseItem):
    """
    Represents a node in the gene regulatory network visualization.

    A node can represent either a regular gene or an input gene. Input genes are
    displayed with thicker borders and slightly different coloring.

    Attributes:
        `name` (str): The unique identifier for this node
        `is_input` (bool): Whether this node represents an input gene
        `radius` (float): The radius of the circular node representation
        `label` (NodeLabel): The text label displaying the node's name
    """

    def __init__(self, name, x, y, radius=20, is_input=False):
        """
        Initialize a new network node.

        Args:
            `name` (str): The unique identifier for this node
            `x` (float): Initial x-coordinate position
            `y` (float): Initial y-coordinate position
            `radius` (float, optional): Node radius in pixels. Defaults to 20.
            `is_input` (bool, optional): Whether this is an input node. Defaults to False.
        """
        super().__init__(0, 0, radius * 2, radius * 2)
        self.name = name
        self.is_input = is_input  # Store whether this is an input node
        self.setPos(x - radius, y - radius)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

        self.radius = radius
        self.setAcceptHoverEvents(True)

        # Add label as child item
        self.label = NodeLabel(name, self)

        # Initialize colors
        self.update_colors()

        # Connect to both palette and color scheme changes
        app = QApplication.instance()
        app.paletteChanged.connect(self.update_colors)
        app.styleHints().colorSchemeChanged.connect(self.update_colors)

    def update_colors(self):
        app = QApplication.instance()
        palette = app.palette()

        # Get base colors from palette
        self.base_color = palette.color(QPalette.ColorRole.Base)
        self.text_color = palette.color(QPalette.ColorRole.Text)
        self.highlight_color = palette.color(QPalette.ColorRole.Highlight)

        # Create a slightly contrasting color for nodes
        if app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
            # In dark mode, make nodes slightly lighter
            base_lightness = 200
            if self.is_input:
                self.node_color = self.base_color.lighter(
                    base_lightness + 20
                )  # Even lighter for input nodes
            else:
                self.node_color = self.base_color.lighter(base_lightness)
        else:
            # In light mode, make nodes slightly darker
            base_darkness = 110
            if self.is_input:
                self.node_color = self.base_color.darker(
                    base_darkness + 10
                )  # Slightly darker for input nodes
            else:
                self.node_color = self.base_color.darker(base_darkness)

        # Update current colors
        self.setBrush(QBrush(self.node_color))

        # Set pen with thicker width for input nodes
        pen = QPen(self.text_color)
        pen.setWidth(3 if self.is_input else 1)
        self.setPen(pen)

        # Force a redraw
        if self.scene():
            self.scene().update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Use highlight color for selection
            self.setBrush(QBrush(self.highlight_color))
            if isinstance(self.scene().views()[0], NetworkView):
                view = self.scene().views()[0]
                if view.mode == EditMode.ADDING_EDGE:
                    view.node_clicked(self)
                else:
                    super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setBrush(QBrush(self.node_color))  # Reset to node color
        if self.scene().views()[0].mode != EditMode.ADDING_EDGE:
            super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        if isinstance(self.scene().views()[0], NetworkView):
            view = self.scene().views()[0]
            if (
                view.mode == EditMode.ADDING_EDGE
                and view.source_node
                and view.source_node != self
            ):
                # Use highlight color for valid target
                self.setBrush(QBrush(self.highlight_color))
            else:
                app = QApplication.instance()

                # Make the node slightly lighter/darker on hover
                if app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
                    hover_color = self.node_color.lighter(120)
                else:
                    hover_color = self.node_color.darker(105)
                self.setBrush(QBrush(hover_color))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(self.node_color))  # Reset to node color
        super().hoverLeaveEvent(event)

    def center(self):
        return self.pos() + QPointF(self.radius, self.radius)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # Update connected edges when node moves
            if isinstance(self.scene().views()[0], NetworkView):
                view = self.scene().views()[0]
                for edge in view.edges:
                    if edge.source_node == self or edge.target_node == self:
                        edge.update_position()
                # Emit the modified signal when node position changes
                view.grn_modified.emit()
        return super().itemChange(change, value)

    def contextMenuEvent(self, event):
        menu = QMenu()
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")

        # Add toggle input/regular action
        toggle_type_action = menu.addAction(
            "Set as Regular" if self.is_input else "Set as Input"
        )

        # Get the action that was clicked
        action = menu.exec(event.screenPos())

        if action == rename_action:
            self.rename_node()
        elif action == delete_action:
            self.delete_node()
        elif action == toggle_type_action:
            self.toggle_type()

    def rename_node(self):
        # Get reference to main window through scene's view
        view = self.scene().views()[0]
        if isinstance(view, NetworkView):
            view.rename_node(self)

    def delete_node(self):
        view = self.scene().views()[0]
        if isinstance(view, NetworkView):
            view.delete_node(self)

    def toggle_type(self):
        view = self.scene().views()[0]
        if isinstance(view, NetworkView):
            view.toggle_node_type(self)


class NodeLabel(QGraphicsItem):
    """
    A text label displayed on a NetworkNode showing its name.

    This class handles the rendering of node names and automatically updates
    its appearance based on the application's color scheme.

    Attributes:
        `text` (str): The text to display (usually the node's name)
        `parent_node` (NetworkNode): The node this label belongs to
        `text_color` (QColor): The current color used for rendering text
    """

    def __init__(self, text, parent_node):
        """
        Initialize a new node label.

        Args:
            `text` (str): The text to display
            `parent_node` (NetworkNode): The node this label belongs to
        """
        super().__init__(parent_node)
        self.text = text
        self.parent_node = parent_node

        # Connect to both palette and color scheme changes
        app = QApplication.instance()
        app.paletteChanged.connect(self.update_colors)
        app.styleHints().colorSchemeChanged.connect(self.update_colors)
        self.update_colors()

    def update_colors(self):
        self.text_color = (
            QApplication.instance().palette().color(QPalette.ColorRole.Text)
        )
        if self.scene():
            self.scene().update()

    def boundingRect(self):
        return QRectF(-20, -20, 40, 40)

    def paint(self, painter, option, widget):
        painter.setPen(QPen(self.text_color))
        painter.drawText(-10, -10, self.text)


class NetworkEdge(QGraphicsLineItem):
    """
    Represents an edge in the gene regulatory network visualization.

    Edges can represent either activation (positive regulation) or inhibition
    (negative regulation) relationships between nodes. The visual appearance
    changes based on the edge type.

    Attributes:
        `source_node` (NetworkNode): The node where the edge starts
        `target_node` (NetworkNode): The node where the edge ends
        `edge_type` (int): 1 for activation, -1 for inhibition
    """

    def __init__(self, source_node, target_node, edge_type=1):
        """
        Initialize a new network edge.

        Args:
            `source_node` (NetworkNode): The node where the edge starts
            `target_node` (NetworkNode): The node where the edge ends
            `edge_type` (int, optional): 1 for activation, -1 for inhibition. Defaults to 1.
        """
        super().__init__()
        self.source_node = source_node
        self.target_node = target_node
        self.edge_type = edge_type  # 1 for activation, -1 for inhibition

        # Connect to both palette and color scheme changes
        app = QApplication.instance()
        app.paletteChanged.connect(self.update_colors)
        app.styleHints().colorSchemeChanged.connect(self.update_colors)

        self.setZValue(-1)  # Draw edges behind nodes
        self.update_colors()
        self.update_position()

    def update_colors(self):
        app = QApplication.instance()
        palette = app.palette()

        if self.edge_type == 1:
            # For activation edges, use Link color if available, otherwise use Highlight
            edge_color = (
                palette.color(QPalette.ColorRole.Link)
                if palette.color(QPalette.ColorRole.Link).isValid()
                else palette.color(QPalette.ColorRole.Highlight)
            )
        else:
            # For inhibition edges, create a red that contrasts with the current theme
            if app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
                # Light red for dark theme
                edge_color = QColor(255, 100, 100)
            else:
                # Dark red for light theme
                edge_color = QColor(180, 0, 0)

        self.setPen(QPen(edge_color, 2))
        if self.scene():
            self.scene().update()

    def update_position(self):
        if not (self.source_node and self.target_node):
            return

        source_pos = self.source_node.center()
        target_pos = self.target_node.center()

        # Calculate vector from source to target
        dx = target_pos.x() - source_pos.x()
        dy = target_pos.y() - source_pos.y()
        length = (dx * dx + dy * dy) ** 0.5

        if length == 0:
            return

        # Normalize vector
        dx /= length
        dy /= length

        # Adjust start and end points to be on the circle edge
        radius = self.source_node.radius
        start_x = source_pos.x() + dx * radius
        start_y = source_pos.y() + dy * radius
        end_x = target_pos.x() - dx * radius
        end_y = target_pos.y() - dy * radius

        self.setLine(start_x, start_y, end_x, end_y)


class EditMode(Enum):
    """
    Enumeration of possible editing modes for the network view.

    Values:
        `NORMAL`: Default mode - allows node movement and selection
        `ADDING_NODE`: Mode for adding new nodes to the network
        `ADDING_EDGE`: Mode for creating edges between nodes
    """

    NORMAL = 0
    ADDING_NODE = 1
    ADDING_EDGE = 2


class NetworkView(QGraphicsView):
    """
    The main view widget for the gene regulatory network editor.

    This class handles the visualization and interaction with the network,
    including node placement, edge creation, and view manipulation (zoom/pan).

    Signals:
        `mode_changed`: Emitted when the editing mode changes
        `status_message`: Emitted when a new status message should be displayed
        `grn_modified`: Emitted when the network is modified
    """

    # Add the signals documentation
    mode_changed = pyqtSignal(EditMode)  # Signal when edit mode changes
    status_message = pyqtSignal(str)  # Signal for status bar updates
    grn_modified = pyqtSignal()  # Signal when network is modified

    def __init__(self, parent=None):
        """
        Initialize the network view.

        Args:
            `parent` (QWidget, optional): Parent widget. Defaults to None.
        """
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        # Initialize GRN
        self.grn = GRN()
        self.nodes = {}
        self.edges = []

        # Replace edge drawing state with mode state
        self._mode = EditMode.NORMAL
        self.source_node = None
        self.temp_line = None
        self.edge_type = 1  # 1 for activation, -1 for inhibition

        # Node addition state
        self.node_type_to_add = None
        self.node_name_to_add = None

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, new_mode):
        if self._mode != new_mode:
            self._mode = new_mode
            self._handle_mode_change()
            self.mode_changed.emit(new_mode)

    def _handle_mode_change(self):
        """
        Handle state changes when the editing mode changes.

        Updates cursor appearance, node dragging capabilities, and status messages
        based on the current editing mode. Also cleans up any temporary items
        from edge creation.
        """
        # Clean up any temporary items
        if self.temp_line:
            self.scene.removeItem(self.temp_line)
            self.temp_line = None

        self.source_node = None

        # Update node dragging flags
        for node in self.nodes.values():
            node.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                self.mode == EditMode.NORMAL,
            )

        # Update cursor and status message
        if self.mode == EditMode.NORMAL:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.status_message.emit("")
        elif self.mode == EditMode.ADDING_EDGE:
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.status_message.emit("Click and drag from source node to create edge")
        elif self.mode == EditMode.ADDING_NODE:
            self.setCursor(Qt.CursorShape.CrossCursor)
            if self.node_type_to_add and self.node_name_to_add:
                self.status_message.emit(
                    f"Click to place {self.node_type_to_add.lower()} node '{self.node_name_to_add}' (Press Esc to cancel)"
                )
            else:
                self.status_message.emit("Click to place node (Press Esc to cancel)")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.mode = EditMode.NORMAL
            self.node_type_to_add = None
            self.node_name_to_add = None
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if (
            self.mode == EditMode.ADDING_NODE
            and event.button() == Qt.MouseButton.LeftButton
        ):
            # Get click position in scene coordinates
            scene_pos = self.mapToScene(event.pos())
            x, y = scene_pos.x(), scene_pos.y()

            # Add the node at click position
            if self.node_type_to_add == "Input":
                self.grn.add_input_species(self.node_name_to_add)
            else:
                self.grn.add_species(self.node_name_to_add, 0.1)

            self.add_node(self.node_name_to_add, x, y)

            # Reset node adding state
            self.mode = EditMode.NORMAL
            self.node_type_to_add = None
            self.node_name_to_add = None

            # Reset cursor and status
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if isinstance(self.parent(), MainWindow):
                self.parent().statusBar().clearMessage()
        else:
            super().mousePressEvent(event)

    def start_add_node(self, node_name, node_type):
        """Start the process of adding a node"""
        # Clean up any ongoing edge creation first
        if self.mode == EditMode.ADDING_EDGE:
            if self.temp_line:
                self.scene.removeItem(self.temp_line)
            self.temp_line = None
            self.source_node = None

        # Set the node properties
        self.node_name_to_add = node_name
        self.node_type_to_add = node_type
        # Change to node adding mode
        self.mode = EditMode.ADDING_NODE

    def add_node(self, name, x=None, y=None):
        if x is None:
            x = np.random.uniform(0, self.width())
        if y is None:
            y = np.random.uniform(0, self.height())

        # Check if this is an input node
        is_input = name in self.grn.input_species_names

        node = NetworkNode(name, x, y, is_input=is_input)
        self.scene.addItem(node)
        self.nodes[name] = node

        self.grn_modified.emit()
        return node

    def node_clicked(self, node):
        """Handle node clicks based on current mode"""
        if self.mode == EditMode.ADDING_EDGE:
            if self.source_node is None:
                # Start edge creation
                self.source_node = node
                source_pos = node.center()

                # Create temp line starting from the node's center
                self.temp_line = QGraphicsLineItem()
                self.temp_line.setLine(
                    source_pos.x(), source_pos.y(), source_pos.x(), source_pos.y()
                )  # Initial line from node to itself
                self.temp_line.setPen(
                    QPen(QColor("blue" if self.edge_type == 1 else "red"), 2)
                )
                self.scene.addItem(self.temp_line)
                self.status_message.emit("Drag to target node to create edge")

    def complete_edge(self, target_node):
        """
        Complete the creation of an edge between nodes.

        Creates both the visual edge and updates the underlying GRN model with
        the new regulatory relationship. The edge type (activation/inhibition)
        determines the regulation type in the model.

        Args:
            `target_node` (NetworkNode): The node where the edge will end
        """
        if self.source_node and self.source_node != target_node:
            edge = NetworkEdge(self.source_node, target_node, self.edge_type)
            self.scene.addItem(edge)
            self.edges.append(edge)

            # Update GRN
            regulator = {
                "name": self.source_node.name,
                "type": self.edge_type,
                "Kd": 5,
                "n": 2,
            }
            product = {"name": target_node.name}
            self.grn.add_gene(10, [regulator], [product])

            # Reset state
            self.mode = EditMode.NORMAL

            self.grn_modified.emit()

    def mouseMoveEvent(self, event):
        if self.source_node and self.temp_line:
            # Update temporary line while dragging
            source_pos = self.source_node.center()
            mouse_pos = self.mapToScene(event.pos())

            # Calculate vector from source to mouse
            dx = mouse_pos.x() - source_pos.x()
            dy = mouse_pos.y() - source_pos.y()
            length = (dx * dx + dy * dy) ** 0.5

            if length > 0:
                # Normalize vector
                dx /= length
                dy /= length

                # Start from edge of source node
                radius = self.source_node.radius
                start_x = source_pos.x() + dx * radius
                start_y = source_pos.y() + dy * radius

                self.temp_line.setLine(start_x, start_y, mouse_pos.x(), mouse_pos.y())

            # Reset all node colors first
            for node in self.nodes.values():
                if node != self.source_node:
                    node.setBrush(QBrush(node.node_color))

            # Highlight valid target nodes
            items = self.items(event.pos())
            for item in items:
                if isinstance(item, NetworkNode) and item != self.source_node:
                    item.setBrush(QBrush(item.highlight_color))
                    break

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.source_node:
            # Check if released over a valid target node
            items = self.items(event.pos())
            target_node = None
            for item in items:
                if isinstance(item, NetworkNode) and item != self.source_node:
                    target_node = item
                    break

            if target_node:
                self.complete_edge(target_node)
            else:
                # Clean up if not released over a valid target
                if self.temp_line:
                    self.scene.removeItem(self.temp_line)
                self.source_node = None
                self.temp_line = None
                self.mode = EditMode.ADDING_EDGE  # Stay in edge mode
                # Return to original message
                self.status_message.emit(
                    "Click and drag from source node to create edge"
                )

            # Reset all node colors
            for node in self.nodes.values():
                node.setBrush(
                    QBrush(node.node_color)
                )  # Use the node's color update method

        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        # Zoom in/out with mouse wheel
        zoomInFactor = 1.05
        zoomOutFactor = 1 / zoomInFactor

        # Save the scene pos
        oldPos = self.mapToScene(event.position().toPoint())

        # Zoom
        if event.angleDelta().y() > 0:
            zoomFactor = zoomInFactor
        else:
            zoomFactor = zoomOutFactor
        self.scale(zoomFactor, zoomFactor)

        # Get the new position
        newPos = self.mapToScene(event.position().toPoint())

        # Move scene to old position
        delta = newPos - oldPos
        self.translate(delta.x(), delta.y())

    def set_edge_mode(self, enabled):
        """Toggle edge creation mode"""
        self.mode = EditMode.ADDING_EDGE if enabled else EditMode.NORMAL

    def rename_node(self, node):
        # Create rename dialog
        dialog = QDialog(self.parent())
        dialog.setWindowTitle("Rename Node")
        layout = QVBoxLayout()

        # Add name input
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("New name:"))
        name_input = QLineEdit()
        name_input.setText(node.name)
        name_layout.addWidget(name_input)
        layout.addLayout(name_layout)

        # Add buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

        # Custom accept handler to validate name
        def handle_accept():
            new_name = name_input.text().strip()
            if not new_name:
                QMessageBox.warning(dialog, "Warning", "Please enter a node name.")
                return
            if new_name in self.nodes and new_name != node.name:
                QMessageBox.warning(
                    dialog, "Warning", "A node with this name already exists."
                )
                return
            dialog.accept()

        button_box.accepted.connect(handle_accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        # Show dialog and process result
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = name_input.text().strip()
            old_name = node.name

            # Update node label
            node.name = new_name
            node.label.text = new_name

            # Update nodes dictionary
            self.nodes[new_name] = self.nodes.pop(old_name)

            # Update GRN
            # First update species name
            for species in self.grn.species:
                if species["name"] == old_name:
                    species["name"] = new_name
                    break

            # Update input species names if necessary
            if old_name in self.grn.input_species_names:
                self.grn.input_species_names.remove(old_name)
                self.grn.input_species_names.append(new_name)

            # Update gene regulators and products
            for gene in self.grn.genes:
                for regulator in gene["regulators"]:
                    if regulator["name"] == old_name:
                        regulator["name"] = new_name
                for product in gene["products"]:
                    if product["name"] == old_name:
                        product["name"] = new_name

            # Force scene update
            self.scene.update()

            self.grn_modified.emit()

    def delete_node(self, node):
        # Confirm deletion
        reply = QMessageBox.question(
            self.parent(),
            "Delete Node",
            f"Are you sure you want to delete node '{node.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Remove connected edges first
            edges_to_remove = []
            for edge in self.edges:
                if edge.source_node == node or edge.target_node == node:
                    edges_to_remove.append(edge)
                    self.scene.removeItem(edge)

            # Remove edges from list
            for edge in edges_to_remove:
                self.edges.remove(edge)

            # Remove node from scene and dictionary
            self.scene.removeItem(node)
            del self.nodes[node.name]

            # Update GRN
            # Remove species
            self.grn.species = [s for s in self.grn.species if s["name"] != node.name]

            # Remove from input species if present
            if node.name in self.grn.input_species_names:
                self.grn.input_species_names.remove(node.name)

            # Remove genes where this node is a product
            self.grn.genes = [
                g
                for g in self.grn.genes
                if not any(p["name"] == node.name for p in g["products"])
            ]

            # Remove this node as a regulator from remaining genes
            for gene in self.grn.genes:
                gene["regulators"] = [
                    r for r in gene["regulators"] if r["name"] != node.name
                ]

                # If a gene has no regulators left, remove it
                if not gene["regulators"]:
                    self.grn.genes.remove(gene)

            # Force scene update
            self.scene.update()

            self.grn_modified.emit()

    def toggle_node_type(self, node):
        """
        Toggle a node between input and regular type.

        Updates both the visual representation and the underlying GRN model.
        Input nodes have no degradation rate and are treated as external inputs
        during simulation.

        Args:
            `node` (NetworkNode): The node to toggle
        """
        if node.is_input:
            # Converting from input to regular
            if node.name in self.grn.input_species_names:
                self.grn.input_species_names.remove(node.name)
                # Add as regular species with default delta
                for species in self.grn.species:
                    if species["name"] == node.name:
                        species["delta"] = 0.1  # Default degradation rate
                        break
        else:
            # Converting from regular to input
            if node.name not in self.grn.input_species_names:
                self.grn.input_species_names.append(node.name)
                # Remove degradation rate as it's not applicable to input species
                for species in self.grn.species:
                    if species["name"] == node.name:
                        if "delta" in species:
                            del species["delta"]
                        break

        # Toggle the is_input flag
        node.is_input = not node.is_input

        # Update node appearance
        node.update_colors()

        # Force scene update
        self.scene.update()

        self.grn_modified.emit()

    def center_on_nodes(self):
        """Center the view on all nodes"""
        if not self.nodes:
            return

        # Calculate bounding rect of all nodes
        nodes_rect = None
        for node in self.nodes.values():
            node_rect = node.sceneBoundingRect()
            if nodes_rect is None:
                nodes_rect = node_rect
            else:
                nodes_rect = nodes_rect.united(node_rect)

        if nodes_rect:
            # Add some padding
            padding = 50
            nodes_rect.adjust(-padding, -padding, padding, padding)
            # Fit the view to the rectangle
            self.fitInView(nodes_rect, Qt.AspectRatioMode.KeepAspectRatio)


class ParameterPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        # Parameter controls
        param_label = QLabel("Model Parameters")
        self.main_layout.addWidget(param_label)

        # Add parameter controls based on params.py
        self.alpha_spin = self.add_parameter_spinbox("Alpha", 0.1, 0.0, 100.0)
        self.kd_spin = self.add_parameter_spinbox("Kd", 1.0, 0.0, 100.0)
        self.delta_spin = self.add_parameter_spinbox("Delta", 0.05, 0.0, 1.0)
        self.n_spin = self.add_parameter_spinbox("n", 2.0, 1.0, 10.0)

        self.main_layout.addStretch()

    def add_parameter_spinbox(self, label, default, min_val, max_val):
        container = QWidget()
        layout = QHBoxLayout()
        layout.addWidget(QLabel(label))
        spinbox = QDoubleSpinBox()
        spinbox.setRange(min_val, max_val)
        spinbox.setValue(default)
        spinbox.setSingleStep(0.1)
        layout.addWidget(spinbox)
        container.setLayout(layout)
        self.main_layout.addWidget(container)
        return spinbox


class SimulationPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        # Simulation controls
        sim_label = QLabel("Simulation Controls")
        layout.addWidget(sim_label)

        # Time settings
        time_widget = QWidget()
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Simulation Time:"))
        self.time_spin = QDoubleSpinBox()
        self.time_spin.setRange(0, 1000)
        self.time_spin.setValue(100)
        time_layout.addWidget(self.time_spin)
        time_widget.setLayout(time_layout)
        layout.addWidget(time_widget)

        # Simulation buttons
        self.run_button = QPushButton("Run Simulation")
        layout.addWidget(self.run_button)

        layout.addStretch()
        self.setLayout(layout)


class SimulationResultsDialog(QWidget):
    """
    Dialog showing simulation results as a line plot.

    Displays the concentration of each species over time using matplotlib.
    Each species is shown in a different color with a legend identifying them.
    """

    def __init__(self, time_points, results, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Simulation Results")
        self.setGeometry(100, 100, 800, 600)

        layout = QVBoxLayout()

        # Create matplotlib figure
        fig = Figure(figsize=(8, 6))
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)

        # Plot results
        ax = fig.add_subplot(111)
        for species_name, values in results.items():
            ax.plot(time_points, values, label=species_name)

        ax.set_xlabel("Time")
        ax.set_ylabel("Concentration")
        ax.set_title("Species Concentrations over Time")
        ax.legend()

        self.setLayout(layout)


class NetworkStateDialog(QDialog):
    """
    Debug dialog showing the internal state of the GRN model.

    Displays a formatted JSON representation of the current network state,
    including species information, input species, and gene regulatory relationships.
    Useful for debugging model generation and simulation issues.
    """

    def __init__(self, network_state, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Network State Debug")
        self.setGeometry(100, 100, 600, 400)

        layout = QVBoxLayout()

        # Create text area
        text_area = QTextEdit()
        text_area.setReadOnly(True)

        # Set the font to the system fixed font
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(QFont().pointSize())
        text_area.setFont(font)

        # Format the network state nicely
        formatted_state = "Species:\n"
        formatted_state += json.dumps(network_state["species"], indent=2)
        formatted_state += "\n\nInput Species:\n"
        formatted_state += json.dumps(network_state["input_species"], indent=2)
        formatted_state += "\n\nGenes:\n"
        formatted_state += json.dumps(network_state["genes"], indent=2)

        text_area.setText(formatted_state)
        layout.addWidget(text_area)

        # Add OK button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        self.setLayout(layout)


class StartupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(f"Welcome to {APP_NAME}")
        self.setMinimumWidth(400)

        # Set application icon
        app_icon = load_app_icon()
        if app_icon:
            self.setWindowIcon(app_icon)
            QApplication.instance().setWindowIcon(app_icon)

        layout = QVBoxLayout()

        # Add logo
        logo_label = create_logo_label()
        if logo_label:
            layout.addWidget(logo_label)

        # Add welcome text
        welcome_text = QLabel(
            f"""
            <h2>Welcome to {APP_NAME}</h2>
            <p>{APP_LONG_DESCRIPTION}</p>
        """
        )
        welcome_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_text.setWordWrap(True)
        welcome_text.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(welcome_text)

        # Add buttons
        button_layout = QVBoxLayout()

        new_button = QPushButton("Create New Network")
        new_button.clicked.connect(self.accept_new)
        button_layout.addWidget(new_button)

        open_button = QPushButton("Open Existing Network")
        open_button.clicked.connect(self.accept_open)
        button_layout.addWidget(open_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Store the result
        self.result_action = "new"

    def accept_new(self):
        self.result_action = "new"
        self.accept()

    def accept_open(self):
        self.result_action = "open"
        self.accept()


class MainWindow(QMainWindow):
    """
    The main application window for the GReNMlin editor.

    This class manages the overall application UI, including the network view,
    parameter panels, and all menu/toolbar actions. It also handles file operations
    and maintains the application state.

    Attributes:
        `current_file` (str): Path to the currently open network file, or None
        `modified` (bool): Whether the network has unsaved changes
        `network_view` (NetworkView): The main network editing widget
        `parameter_panel` (ParameterPanel): Widget for editing model parameters
        `simulation_panel` (SimulationPanel): Widget for running simulations
    """

    def __init__(self):
        """Initialize the main window and set up the user interface."""
        super().__init__()

        # Track file and modification state
        self.current_file = None
        self.modified = False
        self.update_title()

        self.setGeometry(100, 100, 1200, 800)

        # Ensure menu bar is visible with KDE global menu
        if os.environ.get("XDG_CURRENT_DESKTOP", "").upper() == "KDE" and hasattr(
            self, "menuBar"
        ):
            self.menuBar().setNativeMenuBar(False)

        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)

        # Create network view
        self.network_view = NetworkView()
        layout.addWidget(self.network_view)

        # Create right panel with tabs
        right_panel = QTabWidget()
        right_panel.setMaximumWidth(300)

        # Add parameter panel
        self.parameter_panel = ParameterPanel()
        right_panel.addTab(self.parameter_panel, "Parameters")

        # Add simulation panel
        self.simulation_panel = SimulationPanel()
        right_panel.addTab(self.simulation_panel, "Simulation")

        # Add right panel to layout
        layout.addWidget(right_panel)

        # Set up menu bar
        self.setup_menu()

        # Set up toolbar
        self.setup_toolbar()

        # Connect signals
        self.simulation_panel.run_button.clicked.connect(self.run_simulation)

        # Connect network view signals
        self.network_view.mode_changed.connect(self._handle_mode_change)
        self.network_view.status_message.connect(self.statusBar().showMessage)

        # Connect to network changes
        self.network_view.grn_modified.connect(
            self.set_modified
        )  # We'll add this signal

    def set_modified(self, modified=True):
        """
        Mark the current network as modified and update the window title.

        Args:
            `modified` (bool, optional): Whether the network has been modified.
                Defaults to True.
        """
        self.modified = modified
        self.update_title()

    def update_title(self):
        """Update window title based on current file and modification state"""
        if self.current_file:
            filename = os.path.basename(self.current_file)
        else:
            filename = "New network"  # Default name for new networks

        self.setWindowTitle(f"{filename}{'*' if self.modified else ''} - {APP_NAME}")

    def setup_toolbar(self):
        toolbar = self.addToolBar("Edit")

        # Add Node button
        add_node_action = toolbar.addAction("Add Node")
        add_node_action.triggered.connect(self.add_node_dialog)

        # Add Edge button (toggleable)
        self.add_edge_action = toolbar.addAction("Add Edge")
        self.add_edge_action.setCheckable(True)
        self.add_edge_action.toggled.connect(self.toggle_edge_mode)

        # Edge type selection
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("Edge Type:"))
        edge_type = QComboBox()
        edge_type.addItems(["Activation", "Inhibition"])
        edge_type.currentIndexChanged.connect(self.edge_type_changed)
        toolbar.addWidget(edge_type)

    def setup_menu(self):
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        # Connect file menu actions
        new_action = file_menu.addAction("New Network")
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_network)

        open_action = file_menu.addAction(
            "Open Network..."
        )  # Add ellipsis for dialog actions
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.load_network)

        save_action = file_menu.addAction("Save")  # Simplified name
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_network)

        save_as_action = file_menu.addAction("Save As...")
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(lambda: self.save_network(save_as=True))

        # Edit menu
        edit_menu = menubar.addMenu("Edit")
        add_node_action = edit_menu.addAction("Add Node")
        add_node_action.triggered.connect(self.add_node_dialog)

        # View menu
        view_menu = menubar.addMenu("View")
        reset_view_action = view_menu.addAction("Reset View")
        reset_view_action.triggered.connect(self.reset_view)

        # Help menu
        help_menu = menubar.addMenu("Help")
        about_action = help_menu.addAction("About")
        about_action.triggered.connect(self.show_about_dialog)

    def add_node_dialog(self):
        # If we're in edge mode, uncheck the edge button first
        if self.network_view.mode == EditMode.ADDING_EDGE:
            self.add_edge_action.setChecked(False)

        # Create a custom dialog with both name input and node type selection
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Node")
        layout = QVBoxLayout()

        # Add name input
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Node name:"))
        name_input = QLineEdit()
        name_layout.addWidget(name_input)
        layout.addLayout(name_layout)

        # Add type selection with radio buttons
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Node type:"))

        # Create radio buttons
        regular_radio = QRadioButton("Regular")
        input_radio = QRadioButton("Input")
        regular_radio.setChecked(True)  # Set Regular as default

        # Add radio buttons to a button group
        button_group = QButtonGroup()
        button_group.addButton(regular_radio)
        button_group.addButton(input_radio)

        type_layout.addWidget(regular_radio)
        type_layout.addWidget(input_radio)
        layout.addLayout(type_layout)

        # Add buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

        # Custom accept handler to validate name
        def handle_accept():
            name = name_input.text().strip()
            if not name:
                QMessageBox.warning(dialog, "Warning", "Please enter a node name.")
                return
            if name in self.network_view.nodes:
                QMessageBox.warning(
                    dialog, "Warning", "A node with this name already exists."
                )
                return
            dialog.accept()

        button_box.accepted.connect(handle_accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        # Show dialog and process result
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_input.text().strip()
            node_type = "Input" if input_radio.isChecked() else "Regular"
            self.network_view.start_add_node(name, node_type)

    def edge_type_changed(self, index):
        # Update edge type in network view (0 = activation, 1 = inhibition)
        self.network_view.edge_type = 1 if index == 0 else -1

    def run_simulation(self):
        grn = self.network_view.grn
        sim_time = self.simulation_panel.time_spin.value()

        # Make sure we have some nodes
        if not grn.species:
            QMessageBox.warning(
                self, "Warning", "Please add some nodes to the network first."
            )
            return

        # Show debug dialog with network state
        network_state = {
            "species": grn.species,
            "input_species": grn.input_species_names,
            "genes": grn.genes,
        }
        debug_dialog = NetworkStateDialog(network_state, self)
        debug_dialog.exec()

        # TODO: Fix implementation of simulation
        return

        # Get initial conditions and species names
        initial_state = []
        species_names = []
        for species in grn.species:
            species_names.append(species["name"])
            if species["name"] in grn.input_species_names:
                initial_state.append(10.0)  # Default input value
            else:
                initial_state.append(0.0)

        # Run simulation
        try:
            # First generate the model
            grn.generate_model()
            # Then simulate
            time_points, results = simulator.simulate_single(
                grn, initial_state, t_end=sim_time, plot_on=False
            )

            # Convert results to dictionary for plotting
            results_dict = {}
            for i, name in enumerate(species_names):
                results_dict[name] = results[:, i]

            # Show results in new window
            dialog = SimulationResultsDialog(time_points, results_dict, self)
            dialog.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Simulation error: {str(e)}")
            # Print more detailed error information
            import traceback

            traceback.print_exc()

    def toggle_edge_mode(self, enabled):
        self.network_view.set_edge_mode(enabled)

    def new_network(self):
        if self.maybe_save():  # Check if we need to save first
            # Clear the current network
            self.network_view.scene.clear()
            self.network_view.nodes.clear()
            self.network_view.edges.clear()
            self.network_view.grn = GRN()
            self.current_file = None
            self.modified = False
            self.update_title()

    def save_network(self, save_as=False):
        """
        Save the current network to a file.

        Args:
            `save_as` (bool, optional): Whether to show the file dialog even if
                the network has been saved before. Defaults to False.

        Returns:
            bool: True if the network was saved successfully, False otherwise.
        """
        if self.current_file is None or save_as:
            file_name, _ = QFileDialog.getSaveFileName(
                self, "Save Network", "", "GReNMlin Files (*.grn);;All Files (*)"
            )
            if not file_name:
                return False
            if not file_name.endswith(".grn"):
                file_name += ".grn"
            self.current_file = file_name
            self.update_title()

        try:
            # Create network data structure
            network_data = {
                "nodes": [],
                "edges": [],
                "grn": {
                    "species": self.network_view.grn.species,
                    "input_species_names": self.network_view.grn.input_species_names,
                    "genes": self.network_view.grn.genes,
                },
            }

            # Save node positions
            for name, node in self.network_view.nodes.items():
                network_data["nodes"].append(
                    {
                        "name": name,
                        "x": node.pos().x(),
                        "y": node.pos().y(),
                        "is_input": name in self.network_view.grn.input_species_names,
                    }
                )

            # Save edges
            for edge in self.network_view.edges:
                network_data["edges"].append(
                    {
                        "source": edge.source_node.name,
                        "target": edge.target_node.name,
                        "type": edge.edge_type,
                    }
                )

            # Save to file
            with open(self.current_file, "w") as f:
                json.dump(network_data, f, indent=2)

            self.modified = False
            self.update_title()
            self.statusBar().showMessage(f"Network saved to {self.current_file}", 3000)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save network: {str(e)}")
            return False

    def load_network(self):
        """
        Load a network from a file.

        Prompts the user to save any unsaved changes first, then shows a file
        dialog to choose the network file to load. Updates the UI to display
        the loaded network.
        """
        if self.maybe_save():  # Check if we need to save first
            file_name, _ = QFileDialog.getOpenFileName(
                self, "Open Network", "", "GReNMlin Files (*.grn);;All Files (*)"
            )
            if not file_name:
                return

            try:
                with open(file_name, "r") as f:
                    network_data = json.load(f)

                # Clear current network
                self.network_view.scene.clear()
                self.network_view.nodes.clear()
                self.network_view.edges.clear()
                self.network_view.grn = GRN()

                # Restore GRN state
                for species in network_data["grn"]["species"]:
                    if species["name"] in network_data["grn"]["input_species_names"]:
                        self.network_view.grn.add_input_species(species["name"])
                    else:
                        self.network_view.grn.add_species(
                            species["name"], species["delta"]
                        )

                # Create nodes
                for node_data in network_data["nodes"]:
                    self.network_view.add_node(
                        node_data["name"], node_data["x"], node_data["y"]
                    )

                # Create edges
                for edge_data in network_data["edges"]:
                    source_node = self.network_view.nodes[edge_data["source"]]
                    target_node = self.network_view.nodes[edge_data["target"]]
                    edge = NetworkEdge(source_node, target_node, edge_data["type"])
                    self.network_view.scene.addItem(edge)
                    self.network_view.edges.append(edge)

                # Restore genes
                self.network_view.grn.genes = network_data["grn"]["genes"]

                self.current_file = file_name
                self.modified = False
                self.update_title()
                self.statusBar().showMessage(f"Network loaded from {file_name}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load network: {str(e)}")

    def maybe_save(self):
        """
        Check if there are unsaved changes and prompt to save if needed.

        Returns:
            bool: True if it's safe to proceed (changes saved or discarded),
                  False if the operation should be cancelled.
        """
        if not self.modified:
            return True

        # Customize message based on whether it's a new network
        if self.current_file is None:
            message = "Do you want to save the new network?"
        else:
            message = "The network has been modified. Do you want to save your changes?"

        reply = QMessageBox.question(
            self,
            "Save Changes",
            message,
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )

        if reply == QMessageBox.StandardButton.Save:
            return self.save_network()
        elif reply == QMessageBox.StandardButton.Cancel:
            return False
        return True  # Discard was clicked

    def closeEvent(self, event):
        """Handle application closing"""
        if self.maybe_save():
            event.accept()
        else:
            event.ignore()

    def _handle_mode_change(self, mode):
        """Handle network view mode changes"""
        # Update toolbar actions
        self.add_edge_action.setChecked(mode == EditMode.ADDING_EDGE)

    def reset_view(self):
        """Reset view transformation and center on nodes"""
        self.network_view.resetTransform()
        self.network_view.center_on_nodes()

    def show_about_dialog(self):
        about_dialog = QDialog(self)
        about_dialog.setWindowTitle(f"About {APP_NAME}")
        layout = QVBoxLayout()

        # Add logo
        logo_label = create_logo_label()
        if logo_label:
            layout.addWidget(logo_label)

        # Add app info
        info_text = QLabel(
            f"""
            <h2>{APP_NAME} {APP_VERSION}</h2>
            <p>{APP_DESCRIPTION}</p>
            <p>{APP_LONG_DESCRIPTION}</p>
            <p><a href="{GITHUB_URL}">GitHub Repository</a></p>
        """
        )
        info_text.setOpenExternalLinks(True)
        info_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_text.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(info_text)

        # Add OK button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(about_dialog.accept)
        layout.addWidget(button_box)

        about_dialog.setLayout(layout)
        about_dialog.exec()


def load_app_icon():
    icon_path = os.path.join(os.path.dirname(__file__), ICON_FILENAME)
    if os.path.exists(icon_path):
        return QIcon(icon_path)
    return None


def create_logo_label(size=128):
    icon_path = os.path.join(os.path.dirname(__file__), ICON_FILENAME)
    if not os.path.exists(icon_path):
        return None

    logo_label = QLabel()
    pixmap = QPixmap(icon_path)
    scaled_pixmap = pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    logo_label.setPixmap(scaled_pixmap)
    logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return logo_label


def main():
    app = QApplication(sys.argv)

    # Show startup dialog
    startup = StartupDialog()
    if startup.exec() == QDialog.DialogCode.Accepted:
        window = MainWindow()
        if startup.result_action == "open":
            # Trigger open file dialog
            window.load_network()
        window.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
