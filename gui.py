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
import uuid
from enum import Enum

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal, QLineF, QSizeF
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
    QPainterPath,
    QPolygonF,
)
import math
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


class EdgeType(Enum):
    """
    Enumeration of possible edge types in the network.

    Values:
        `ACTIVATION`: Positive regulation (shown as blue/highlight colored edge)
        `INHIBITION`: Negative regulation (shown as red edge)
    """

    ACTIVATION = 1
    INHIBITION = -1


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

    def __init__(self, species_name="", grn=None, x=0.0, y=0.0, radius=20, logic_type="and", alpha=10.0, display_name=None):
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
        self.species_name = species_name
        self.grn = grn
        self.logic_type = logic_type
        self.alpha = alpha
        self.display_name = display_name or species_name  # Allow different display name than species name
        self.node_id = str(uuid.uuid4())
        self.setPos(x - radius, y - radius)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

        self.radius = radius
        self.setAcceptHoverEvents(True)

        # Add label as child item
        self.label = NodeLabel(self.display_name, self)

        # Initialize colors
        self.update_colors()

        # Connect to both palette and color scheme changes
        app = QApplication.instance()
        app.paletteChanged.connect(self.update_colors)
        app.styleHints().colorSchemeChanged.connect(self.update_colors)
        self.setZValue(1)  # Edges should have setZValue(-1)

    @property
    def is_input(self):
        return self.species_name in self.grn.input_species_names

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
                    super().mousePressEvent(event)  # Allow normal drag behavior
            self.update()

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

        # Get the action that was clicked
        action = menu.exec(event.screenPos())

        if action == rename_action:
            self.rename_node()
        elif action == delete_action:
            self.delete_node()

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

class ArrowLineItem(QGraphicsItem):
    """
    A line item with an arrow head.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line = QLineF()
        self.pen = QPen()
        self.arrow_size = 20
        self.arrow_angle = 60

    def setPen(self, pen):
        self.pen = pen
        self.update()

    def setLine(self, x1, y1, x2, y2):
        self.line = QLineF(x1, y1, x2, y2)
        self.update()

    def boundingRect(self):
        extra = (self.pen.width() + self.arrow_size) / 2.0
        return QRectF(self.line.p1(),
                     QSizeF(self.line.p2().x() - self.line.p1().x(),
                           self.line.p2().y() - self.line.p1().y())).normalized().adjusted(-extra, -extra, extra, extra)

    def paint(self, painter, option, widget):
        painter.setPen(self.pen)
        painter.setBrush(QBrush(self.pen.color()))

        # Draw the line
        painter.drawLine(self.line)

        # Draw the arrow
        if self.line.length() > 0:
            angle = math.acos(self.line.dx() / self.line.length())
            if self.line.dy() >= 0:
                angle = 2 * math.pi - angle

            # Calculate arrow points
            arrow_p1 = self.line.p2() - QPointF(
                math.sin(angle + math.pi / 180 * self.arrow_angle) * self.arrow_size,
                math.cos(angle + math.pi / 180 * self.arrow_angle) * self.arrow_size)
            arrow_p2 = self.line.p2() - QPointF(
                math.sin(angle + math.pi - math.pi / 180 * self.arrow_angle) * self.arrow_size,
                math.cos(angle + math.pi - math.pi / 180 * self.arrow_angle) * self.arrow_size)

            # Create arrow polygon
            arrow_head = QPolygonF()
            arrow_head.append(self.line.p2())
            arrow_head.append(arrow_p1)
            arrow_head.append(arrow_p2)

            # Draw the arrow head
            painter.drawPolygon(arrow_head)

class NetworkEdge(QGraphicsLineItem):
    """
    Represents an edge in the gene regulatory network visualization.

    Edges can represent either activation (positive regulation) or inhibition
    (negative regulation) relationships between nodes. The visual appearance
    changes based on the edge type.

    Attributes:
        `source_node` (NetworkNode): The node where the edge starts
        `target_node` (NetworkNode): The node where the edge ends
        `edge_type` (EdgeType): The type of regulation (ACTIVATION or INHIBITION)
    """

    def __init__(self, source_node, target_node, edge_type=EdgeType.ACTIVATION, kd=5.0, n=2.0):
        """
        Initialize a new network edge.

        Args:
            `source_node` (NetworkNode): The node where the edge starts
            `target_node` (NetworkNode): The node where the edge ends
            `edge_type` (EdgeType, optional): Type of regulation. Defaults to EdgeType.ACTIVATION.
        """
        super().__init__()
        self.source_node = source_node
        self.target_node = target_node
        self.edge_type = edge_type
        self.kd = kd
        self.n = n

        # Connect to both palette and color scheme changes
        app = QApplication.instance()
        app.paletteChanged.connect(self.update_colors)
        app.styleHints().colorSchemeChanged.connect(self.update_colors)

        # Make edge selectable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.default_width = 2
        self.selected_width = 4
        self.visible_line = ArrowLineItem(self)  # Create visible child line

        self.setZValue(-1)  # Draw edges behind nodes

        # Add invisible wider line for easier selection
        self.setPen(QPen(Qt.PenStyle.NoPen))  # Make the actual line invisible
        self.update_colors()  # This will set up the visible line's appearance
        self.update_position()

    def update_colors(self):
        app = QApplication.instance()
        palette = app.palette()

        if self.edge_type == EdgeType.ACTIVATION:
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

        # Use thicker line when selected, thinner when not
        width = self.default_width if not self.isSelected() else self.selected_width
        visible_pen = QPen(edge_color, width)
        hover_pen = QPen(Qt.PenStyle.NoPen)  # Invisible pen for the wider hoverable area

        self.visible_line.setPen(visible_pen)
        self.setPen(hover_pen)
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

        # Update both the selection area and visible line
        self.setLine(start_x, start_y, end_x, end_y)
        self.visible_line.setLine(start_x, start_y, end_x, end_y)

    def shape(self):
        # Create a wider shape for easier selection
        path = QPainterPath()
        line = self.line()

        # Calculate a polygon that represents a thicker line
        vector = line.p2() - line.p1()
        length = (vector.x() * vector.x() + vector.y() * vector.y()) ** 0.5
        if length == 0:
            return path

        # Normalize vector and create perpendicular vector
        vector_norm = vector / length
        perpendicular = QPointF(-vector_norm.y(), vector_norm.x())

        # Width of the selection area
        width = 10

        # Create a polygon around the line
        points = [
            line.p1() + perpendicular * width,
            line.p2() + perpendicular * width,
            line.p2() - perpendicular * width,
            line.p1() - perpendicular * width
        ]

        # Add polygon to path
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        path.closeSubpath()

        return path

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            # Update the line width when selection changes
            self.update_colors()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Toggle selection
            self.setSelected(not self.isSelected())
            event.accept()
        else:
            super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        edit_action = menu.addAction("Edit Parameters")
        delete_action = menu.addAction("Delete")

        action = menu.exec(event.screenPos())

        if action == edit_action:
            self.edit_parameters()
        elif action == delete_action:
            self.delete_edge()

    def edit_parameters(self):
        dialog = QDialog()
        dialog.setWindowTitle("Edit Edge Parameters")
        layout = QVBoxLayout()

        # Kd input
        kd_layout = QHBoxLayout()
        kd_layout.addWidget(QLabel("Kd:"))
        kd_spin = QDoubleSpinBox()
        kd_spin.setRange(0.1, 100.0)
        kd_spin.setValue(self.kd)
        kd_spin.setSingleStep(0.1)
        kd_layout.addWidget(kd_spin)
        layout.addLayout(kd_layout)

        # n input
        n_layout = QHBoxLayout()
        n_layout.addWidget(QLabel("n:"))
        n_spin = QDoubleSpinBox()
        n_spin.setRange(1.0, 10.0)
        n_spin.setValue(self.n)
        n_spin.setSingleStep(0.1)
        n_layout.addWidget(n_spin)
        layout.addLayout(n_layout)

        # Edge type selection
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Regulation:"))
        type_combo = QComboBox()
        type_combo.addItems(["Activation", "Inhibition"])
        type_combo.setCurrentIndex(0 if self.edge_type == EdgeType.ACTIVATION else 1)
        type_layout.addWidget(type_combo)
        layout.addLayout(type_layout)

        # Add buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Update edge parameters
            self.kd = kd_spin.value()
            self.n = n_spin.value()
            old_type = self.edge_type
            self.edge_type = EdgeType.ACTIVATION if type_combo.currentIndex() == 0 else EdgeType.INHIBITION

            # Update the visual appearance
            self.update_colors()

            # Update the GRN model
            view = self.scene().views()[0]
            if isinstance(view, NetworkView):
                # Find and update the corresponding gene in the GRN
                for gene in view.grn.genes:
                    for regulator in gene["regulators"]:
                        if (regulator["name"] == self.source_node.species_name and
                            gene["products"][0]["name"] == self.target_node.species_name):
                            regulator["Kd"] = self.kd
                            regulator["n"] = self.n
                            regulator["type"] = self.edge_type.value
                            view.grn_modified.emit()
                            break

    def delete_edge(self):
        view = self.scene().views()[0]
        if isinstance(view, NetworkView):
            # Remove the edge from the view
            view.edges.remove(self)
            self.scene().removeItem(self)

            # Remove corresponding gene from GRN
            view.grn.genes = [g for g in view.grn.genes
                            if not (any(r["name"] == self.source_node.species_name for r in g["regulators"]) and
                                  any(p["name"] == self.target_node.species_name for p in g["products"]))]
            view.grn_modified.emit()


class NetworkView(QGraphicsView):
    """
    The main view widget for the gene regulatory network editor.

    This class handles the visualization and interaction with the network,
    including node placement, edge creation, and view manipulation (zoom/pan).

    Attributes:
        `grn` (GRN): The underlying gene regulatory network model
        `nodes` (dict): Mapping of node names to NetworkNode objects
        `edges` (list): List of NetworkEdge objects in the network
        `mode` (EditMode): Current editing mode (NORMAL, ADDING_NODE, ADDING_EDGE)
        `edge_type` (EdgeType): Type of edge to create (ACTIVATION or INHIBITION)
        `source_node` (NetworkNode): Source node when creating an edge
        `temp_line` (QGraphicsLineItem): Temporary line shown while creating an edge

    Signals:
        `mode_changed`: Emitted when the editing mode changes
        `status_message`: Emitted when a new status message should be displayed
        `grn_modified`: Emitted when the network is modified
    """

    # Add the signals documentation
    mode_changed = pyqtSignal(EditMode)  # Signal when edit mode changes
    status_message = pyqtSignal(str)  # Signal for status bar updates
    grn_modified = pyqtSignal()  # Signal when network is modified
    item_selected = pyqtSignal(object)  # Signal when a node or edge is selected

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
        self.setInteractive(True)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)  # Allow selection rectangle

        # Initialize GRN
        self.grn = GRN()
        self.nodes = {}
        self.edges = []

        # Replace edge drawing state with mode state
        self._mode = EditMode.NORMAL
        self.source_node = None
        self.temp_line = None
        self.edge_type = EdgeType.ACTIVATION

        # Node addition state
        self.node_logic_to_add = None
        self.node_display_name = None
        self.node_name_to_add = None
        self.node_alpha_to_add = None

        self.scene.selectionChanged.connect(self.handle_selection_changed)

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, new_mode):
        if self._mode != new_mode:
            self._mode = new_mode
            self._handle_mode_change()
            self.mode_changed.emit(new_mode)

    def handle_selection_changed(self):
        selected_items = self.scene.selectedItems()
        if len(selected_items) == 1:
            item = selected_items[0]
            if isinstance(item, (NetworkNode, NetworkEdge)):
                self.item_selected.emit(item)
        else:
            self.item_selected.emit(None)

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
            self.status_message.emit("Click to place node (Press Esc to cancel)")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.mode = EditMode.NORMAL
            self.node_logic_to_add = None
            self.node_name_to_add = None
            self.node_alpha_to_add = None
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if (self.mode == EditMode.ADDING_NODE and
            event.button() == Qt.MouseButton.LeftButton):
            scene_pos = self.mapToScene(event.pos())
            x, y = scene_pos.x(), scene_pos.y()

            self.add_node(
                species_name=self.node_name_to_add,
                logic_type=self.node_logic_to_add,
                x=x,
                y=y,
                display_name=self.node_display_name
            )

            # Reset node adding state
            self.mode = EditMode.NORMAL
            self.node_logic_to_add = None
            self.node_name_to_add = None
            self.node_alpha_to_add = None
            self.node_display_name = None

            # Reset cursor and status
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if isinstance(self.parent(), MainWindow):
                self.parent().statusBar().clearMessage()
        else:
            super().mousePressEvent(event)

    def start_add_node(self, node_name, logic_type, alpha, display_name):
        """Start the process of adding a node"""
        # Clean up any ongoing edge creation first
        if self.mode == EditMode.ADDING_EDGE:
            if self.temp_line:
                self.scene.removeItem(self.temp_line)
            self.temp_line = None
            self.source_node = None

        # Set the node properties
        self.node_name_to_add = node_name
        self.node_logic_to_add = logic_type
        self.node_alpha_to_add = alpha
        self.node_display_name = display_name  # Store display name

        # Change to node adding mode
        self.mode = EditMode.ADDING_NODE

    def add_node(self, species_name, logic_type, x=None, y=None, display_name=None):
        if x is None:
            x = np.random.uniform(0, self.width())
        if y is None:
            y = np.random.uniform(0, self.height())

        node = NetworkNode(
                species_name=species_name,
                grn=self.grn,
                x=x,
                y=y,
                logic_type=logic_type,  # Now correctly passing logic_type
                display_name=display_name
            )
        self.scene.addItem(node)
        self.nodes[node.node_id] = node

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
                color = "blue" if self.edge_type == EdgeType.ACTIVATION else "red"
                self.temp_line.setPen(QPen(QColor(color), 2))
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

            # Update GRN with edge parameters
            regulator = {
                "name": self.source_node.species_name,
                "type": self.edge_type.value,
                "Kd": edge.kd,
                "n": edge.n,
            }
            product = {"name": target_node.species_name}
            self.grn.add_gene(target_node.alpha, [regulator], [product], target_node.logic_type)

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
        dialog = QDialog(self.parent())
        dialog.setWindowTitle("Edit Node Display Name")
        layout = QVBoxLayout()

        # Add display name input
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Display name:"))
        name_input = QLineEdit()
        name_input.setText(node.display_name)
        name_layout.addWidget(name_input)
        layout.addLayout(name_layout)

        # Show the species name (read-only)
        species_layout = QHBoxLayout()
        species_layout.addWidget(QLabel("Species:"))
        species_label = QLabel(node.species_name)
        species_label.setStyleSheet("font-weight: bold;")
        species_layout.addWidget(species_label)
        layout.addLayout(species_layout)

        # Add buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_display_name = name_input.text().strip()
            if not new_display_name:
                new_display_name = node.species_name  # Reset to species name if empty

            # Update node display
            node.display_name = new_display_name
            node.label.text = new_display_name

            # Force scene update
            self.scene.update()

            self.grn_modified.emit()

    def delete_node(self, node):
        # Confirm deletion
        reply = QMessageBox.question(
            self.parent(),
            "Delete Node",
            f"Are you sure you want to delete node '{node.label.text}'?",
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
            del self.nodes[node.node_id]

            # Update GRN
            # Remove species
            self.grn.species = [s for s in self.grn.species if s["name"] != node.species_name]

            # Remove from input species if present
            if node.species_name in self.grn.input_species_names:
                self.grn.input_species_names.remove(node.species_name)

            # Remove genes where this node is a product
            self.grn.genes = [
                g
                for g in self.grn.genes
                if not any(p["name"] == node.species_name for p in g["products"])
            ]

            # Remove this node as a regulator from remaining genes
            for gene in self.grn.genes:
                gene["regulators"] = [
                    r for r in gene["regulators"] if r["name"] != node.species_name
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
            # Converting from input to regular - show dialog for delta
            dialog = QDialog(self.parent())
            dialog.setWindowTitle("Set Degradation Rate")
            layout = QVBoxLayout()

            # Add delta input
            delta_layout = QHBoxLayout()
            delta_layout.addWidget(QLabel("Delta (degradation rate):"))
            delta_spin = QDoubleSpinBox()
            delta_spin.setRange(0, 1.0)
            delta_spin.setSingleStep(0.1)
            delta_spin.setValue(0.1)
            delta_spin.setDecimals(3)
            delta_layout.addWidget(delta_spin)
            layout.addLayout(delta_layout)

            # Add buttons
            button_box = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)
            layout.addWidget(button_box)

            dialog.setLayout(layout)

            if dialog.exec() == QDialog.DialogCode.Accepted:
                delta = delta_spin.value()
                # Converting from input to regular
                self.grn.input_species_names.remove(node.species_name)
                # Add as regular species with specified delta
                for species in self.grn.species:
                    if species["name"] == node.species_name:
                        species["delta"] = delta
                        break
        else:
            # Converting from regular to input
            if node.species_name not in self.grn.input_species_names:
                self.grn.input_species_names.append(node.species_name)
                # Remove degradation rate as it's not applicable to input species
                for species in self.grn.species:
                    if species["name"] == node.species_name:
                        if "delta" in species:
                            del species["delta"]
                        break

        # Update node appearance (will use new is_input status)
        node.update_colors()

        # Force scene update
        self.scene.update()
        self.grn_modified.emit()

    def center_on_nodes(self):
        """Center the view on all nodes"""
        if not self.nodes:
            return

        min_x = float('inf')
        min_y = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')

        # Include all nodes in calculation
        for node in self.nodes.values():
            rect = node.sceneBoundingRect()
            min_x = min(min_x, rect.left())
            min_y = min(min_y, rect.top())
            max_x = max(max_x, rect.right())
            max_y = max(max_y, rect.bottom())

        # Include all edges in calculation
        for edge in self.edges:
            line = edge.line()
            min_x = min(min_x, min(line.x1(), line.x2()))
            min_y = min(min_y, min(line.y1(), line.y2()))
            max_x = max(max_x, max(line.x1(), line.x2()))
            max_y = max(max_y, max(line.y1(), line.y2()))

        if min_x != float('inf'):  # Check if we found any items
            # Create scene rect with padding
            padding = 50
            scene_rect = QRectF(
                min_x - padding,
                min_y - padding,
                max_x - min_x + 2*padding,
                max_y - min_y + 2*padding
            )

            # Update scene rect and fit view
            self.scene.setSceneRect(scene_rect)
            self.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def clear(self):
        """Clear the network view"""
        self.scene.clear()
        self.nodes.clear()
        self.edges.clear()
        self.grn = GRN()


class ParameterPanel(QWidget):
    def __init__(self, network_view, parent=None):
        super().__init__(parent)
        self.network_view = network_view
        self.main_layout = QVBoxLayout()
        self.setLayout(self.main_layout)

        # Store currently selected item
        self.selected_item = None

        # Create species selector and parameters
        self.species_panel = self.create_species_parameters()

        # Create stacked panels for different types of parameters
        self.node_params = self.create_node_parameters()
        self.edge_params = self.create_edge_parameters()

        # Add all parameter widgets
        self.main_layout.addWidget(self.species_panel)
        self.main_layout.addWidget(self.node_params)
        self.main_layout.addWidget(self.edge_params)

        self.node_params.hide()
        self.edge_params.hide()

        self.main_layout.addStretch()

    def create_species_parameters(self):
        widget = QWidget()
        layout = QVBoxLayout()

        # Title
        title = QLabel("Species Parameters")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        # Species selector
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Select species:"))
        self.species_combo = QComboBox()
        self.species_combo.currentTextChanged.connect(self.on_species_selected)
        selector_layout.addWidget(self.species_combo)
        layout.addLayout(selector_layout)

        # Species type
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Type:"))
        self.species_type_combo = QComboBox()
        self.species_type_combo.addItems(["Regular", "Input"])
        type_layout.addWidget(self.species_type_combo)
        layout.addLayout(type_layout)

        # Delta (degradation rate)
        delta_layout = QHBoxLayout()
        delta_layout.addWidget(QLabel("Delta:"))
        self.delta_spin = QDoubleSpinBox()
        self.delta_spin.setRange(0.0, 1.0)
        self.delta_spin.setSingleStep(0.01)
        self.delta_spin.setDecimals(3)
        delta_layout.addWidget(self.delta_spin)
        layout.addLayout(delta_layout)

        # Save button
        self.save_species_button = QPushButton("Apply Changes")
        self.save_species_button.clicked.connect(self.save_species_parameters)
        layout.addWidget(self.save_species_button)

        widget.setLayout(layout)
        return widget

    def create_node_parameters(self):
        widget = QWidget()
        layout = QVBoxLayout()

        # Title
        title = QLabel("Node Parameters")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        # Species selection
        species_layout = QHBoxLayout()
        species_layout.addWidget(QLabel("Species:"))
        self.node_species_combo = QComboBox()  # Changed from label to combo box
        species_layout.addWidget(self.node_species_combo)
        layout.addLayout(species_layout)

        # Display name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Display name:"))
        self.display_name_edit = QLineEdit()
        name_layout.addWidget(self.display_name_edit)
        layout.addLayout(name_layout)

        # Alpha value
        alpha_layout = QHBoxLayout()
        alpha_layout.addWidget(QLabel("Alpha:"))
        self.alpha_spin = QDoubleSpinBox()
        self.alpha_spin.setRange(0.0, 100.0)
        self.alpha_spin.setSingleStep(0.1)
        alpha_layout.addWidget(self.alpha_spin)
        layout.addLayout(alpha_layout)

        # Logic type
        logic_layout = QHBoxLayout()
        logic_layout.addWidget(QLabel("Logic type:"))
        self.logic_combo = QComboBox()
        self.logic_combo.addItems(["and", "or"])
        logic_layout.addWidget(self.logic_combo)
        layout.addLayout(logic_layout)

        # Save button
        self.save_node_button = QPushButton("Apply Changes")
        self.save_node_button.clicked.connect(self.save_node_parameters)
        layout.addWidget(self.save_node_button)

        widget.setLayout(layout)
        return widget

    def create_edge_parameters(self):
        widget = QWidget()
        layout = QVBoxLayout()

        # Title
        title = QLabel("Edge Parameters")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        # Source and target labels
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("Source:"))
        self.source_label = QLabel()
        self.source_label.setStyleSheet("font-weight: bold;")
        source_layout.addWidget(self.source_label)
        layout.addLayout(source_layout)

        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel("Target:"))
        self.target_label = QLabel()
        self.target_label.setStyleSheet("font-weight: bold;")
        target_layout.addWidget(self.target_label)
        layout.addLayout(target_layout)

        # Edge type
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Type:"))
        self.edge_type_combo = QComboBox()
        self.edge_type_combo.addItems(["Activation", "Inhibition"])
        type_layout.addWidget(self.edge_type_combo)
        layout.addLayout(type_layout)

        # Kd value
        kd_layout = QHBoxLayout()
        kd_layout.addWidget(QLabel("Kd:"))
        self.kd_spin = QDoubleSpinBox()
        self.kd_spin.setRange(0.1, 100.0)
        self.kd_spin.setSingleStep(0.1)
        kd_layout.addWidget(self.kd_spin)
        layout.addLayout(kd_layout)

        # n value
        n_layout = QHBoxLayout()
        n_layout.addWidget(QLabel("n:"))
        self.n_spin = QDoubleSpinBox()
        self.n_spin.setRange(1.0, 10.0)
        self.n_spin.setSingleStep(0.1)
        n_layout.addWidget(self.n_spin)
        layout.addLayout(n_layout)

        # Save button
        self.save_edge_button = QPushButton("Apply Changes")
        self.save_edge_button.clicked.connect(self.save_edge_parameters)
        layout.addWidget(self.save_edge_button)

        widget.setLayout(layout)
        return widget


    def update_species_list(self, grn):
        """Update the species combo box with current species"""
        current_text = self.species_combo.currentText()
        self.species_combo.clear()
        self.species_combo.addItems(sorted(grn.species_names))

        # Try to restore the previous selection
        index = self.species_combo.findText(current_text)
        if index >= 0:
            self.species_combo.setCurrentIndex(index)
        elif self.species_combo.count() > 0:
            self.species_combo.setCurrentIndex(0)

    def on_species_selected(self, species_name):
        """Handle species selection from combo box"""
        if not species_name:
            return

        # Use the stored network_view reference
        species_info = next((s for s in self.network_view.grn.species if s["name"] == species_name), None)
        if species_info:
            is_input = species_name in self.network_view.grn.input_species_names
            self.species_type_combo.setCurrentText("Input" if is_input else "Regular")
            self.delta_spin.setValue(species_info.get("delta", 0.1))
            self.delta_spin.setEnabled(not is_input)


    def save_species_parameters(self):
        species_name = self.species_combo.currentText()
        if not species_name:
            return

        # Use the stored network_view reference
        view = self.network_view

        # Get new values
        new_type = self.species_type_combo.currentText()
        new_delta = self.delta_spin.value()

        # Update the GRN
        is_currently_input = species_name in view.grn.input_species_names
        will_be_input = new_type == "Input"

        if is_currently_input != will_be_input:
            # Type changed
            if will_be_input:
                # Convert to input species
                view.grn.input_species_names.append(species_name)
                # Remove delta from species info
                for species in view.grn.species:
                    if species["name"] == species_name and "delta" in species:
                        del species["delta"]
            else:
                # Convert to regular species
                view.grn.input_species_names.remove(species_name)
                # Add delta to species info
                for species in view.grn.species:
                    if species["name"] == species_name:
                        species["delta"] = new_delta
                        break
        elif not will_be_input:
            # Update delta for regular species
            for species in view.grn.species:
                if species["name"] == species_name:
                    species["delta"] = new_delta
                    break

        # Update UI
        self.delta_spin.setEnabled(not will_be_input)

        # Update all nodes of this species
        for node in view.nodes.values():
            if node.species_name == species_name:
                node.update_colors()

        view.grn_modified.emit()

    def show_node_parameters(self, node):
        self.selected_item = node
        self.species_panel.hide()
        self.edge_params.hide()
        self.node_params.show()

        # Update species combo box with all available species
        current_species = node.species_name
        self.node_species_combo.clear()
        self.node_species_combo.addItems(sorted(self.network_view.grn.species_names))

        # Set current values
        index = self.node_species_combo.findText(current_species)
        if index >= 0:
            self.node_species_combo.setCurrentIndex(index)
        self.display_name_edit.setText(node.display_name)
        self.alpha_spin.setValue(node.alpha)
        self.logic_combo.setCurrentText(node.logic_type)

    def show_edge_parameters(self, edge):
        self.selected_item = edge
        self.species_panel.hide()
        self.node_params.hide()
        self.edge_params.show()

        # Update values
        self.source_label.setText(edge.source_node.display_name)
        self.target_label.setText(edge.target_node.display_name)
        self.edge_type_combo.setCurrentIndex(0 if edge.edge_type == EdgeType.ACTIVATION else 1)
        self.kd_spin.setValue(edge.kd)
        self.n_spin.setValue(edge.n)

    def clear_parameters(self):
        """Show species parameters when nothing is selected"""
        self.selected_item = None
        self.node_params.hide()
        self.edge_params.hide()
        self.species_panel.show()

    def save_node_parameters(self):
        if not isinstance(self.selected_item, NetworkNode):
            return

        node = self.selected_item
        old_species = node.species_name
        new_species = self.node_species_combo.currentText()

        # Update node parameters
        node.species_name = new_species
        node.display_name = self.display_name_edit.text()
        node.label.text = node.display_name
        node.alpha = self.alpha_spin.value()
        node.logic_type = self.logic_combo.currentText()

        # If species changed, we need to update the GRN
        if old_species != new_species:
            view = self.network_view
            # Update any edges that use this node
            for edge in view.edges:
                if edge.source_node == node or edge.target_node == node:
                    # Find and update the corresponding gene in the GRN
                    for gene in view.grn.genes:
                        # Update regulators
                        for regulator in gene["regulators"]:
                            if regulator["name"] == old_species:
                                regulator["name"] = new_species
                        # Update products
                        for product in gene["products"]:
                            if product["name"] == old_species:
                                product["name"] = new_species

        # Update node appearance (in case input/regular status changed)
        node.update_colors()

        # Update scene
        if node.scene():
            node.scene().update()

        # Emit modification signal
        self.network_view.grn_modified.emit()

    def save_edge_parameters(self):
        if not isinstance(self.selected_item, NetworkEdge):
            return

        edge = self.selected_item
        # Update edge parameters
        edge.edge_type = EdgeType.ACTIVATION if self.edge_type_combo.currentText() == "Activation" else EdgeType.INHIBITION
        edge.kd = self.kd_spin.value()
        edge.n = self.n_spin.value()

        # Update visual appearance
        edge.update_colors()

        # Update GRN model
        view = edge.scene().views()[0]
        if isinstance(view, NetworkView):
            # Find and update the corresponding gene in the GRN
            for gene in view.grn.genes:
                for regulator in gene["regulators"]:
                    if (regulator["name"] == edge.source_node.species_name and
                        gene["products"][0]["name"] == edge.target_node.species_name):
                        regulator["Kd"] = edge.kd
                        regulator["n"] = edge.n
                        regulator["type"] = edge.edge_type.value
                        view.grn_modified.emit()
                        break

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

        # t_single settings
        t_single_widget = QWidget()
        t_single_layout = QHBoxLayout()
        t_single_layout.addWidget(QLabel("Time per Input Combination (t_single):"))
        self.t_single_spin = QDoubleSpinBox()
        self.t_single_spin.setRange(0, 1000)
        self.t_single_spin.setValue(250)
        t_single_layout.addWidget(self.t_single_spin)
        t_single_widget.setLayout(t_single_layout)
        layout.addWidget(t_single_widget)

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

class SingleSimulationDialog(QDialog):
    """
    Dialog for visualizing single simulation results.

    Displays a graph of the simulation's time vs. species concentrations.
    """
    def __init__(self, T, Y, species_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Single Simulation Results")
        self.setGeometry(100, 100, 800, 600)

        layout = QVBoxLayout()

        # Create matplotlib figure
        figure = Figure()
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)

        # Plot data
        for i, species in enumerate(species_names):
            ax.plot(T, Y[:, i], label=species)

        ax.set_title("Single Simulation")
        ax.set_xlabel("Time")
        ax.set_ylabel("Concentration")
        ax.legend()

        layout.addWidget(canvas)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        self.setLayout(layout)

class SequenceSimulationDialog(QDialog):
    """
    Dialog for visualizing sequence simulation results.

    Displays a graph of time vs. species concentrations for a sequence of inputs.
    """
    def __init__(self, T, Y, species_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sequence Simulation Results")
        self.setGeometry(100, 100, 800, 600)

        layout = QVBoxLayout()

        # Create matplotlib figure
        figure = Figure()
        canvas = FigureCanvas(figure)
        ax = figure.add_subplot(111)

        # Plot data
        for i, species in enumerate(species_names):
            ax.plot(T, Y[:, i], label=species)

        ax.set_title("Sequence Simulation")
        ax.set_xlabel("Time")
        ax.set_ylabel("Concentration")
        ax.legend()

        layout.addWidget(canvas)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

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

        # Add button box with OK and Copy buttons
        button_box = QDialogButtonBox()
        ok_button = button_box.addButton(QDialogButtonBox.StandardButton.Ok)
        copy_button = button_box.addButton(
            "Copy to Clipboard", QDialogButtonBox.ButtonRole.ActionRole
        )

        # Connect button signals
        ok_button.clicked.connect(self.accept)
        copy_button.clicked.connect(
            lambda: QApplication.clipboard().setText(formatted_state)
        )

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

        # Initialize state
        self.current_file = None
        self.modified = False
        self.update_title()

        self.setup_ui()
        self.setup_signals()

    def setup_ui(self):
        """Set up the user interface components."""
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
        self.parameter_panel = ParameterPanel(self.network_view)
        right_panel.addTab(self.parameter_panel, "Parameters")

        # Add simulation panel
        self.simulation_panel = SimulationPanel()
        right_panel.addTab(self.simulation_panel, "Simulation")

        # Add right panel to layout
        layout.addWidget(right_panel)

        # Set up menu and toolbar
        self.setup_menu()
        self.setup_toolbar()

    def setup_signals(self):
        """Connect all signals to their slots."""
        # Simulation panel signals
        self.simulation_panel.run_button.clicked.connect(self.run_simulation)

        # Network view signals
        self.network_view.mode_changed.connect(self.on_mode_changed)
        self.network_view.status_message.connect(self.statusBar().showMessage)
        self.network_view.grn_modified.connect(self.on_network_modified)
        self.network_view.item_selected.connect(self.handle_item_selected)
        self.network_view.grn_modified.connect(self.update_species_list)

    def update_species_list(self):
        """Update the species list in the parameter panel"""
        self.parameter_panel.update_species_list(self.network_view.grn)

    def handle_item_selected(self, item):
        if isinstance(item, NetworkNode):
            self.parameter_panel.show_node_parameters(item)
        elif isinstance(item, NetworkEdge):
            self.parameter_panel.show_edge_parameters(item)
        else:
            self.parameter_panel.clear_parameters()

    def on_mode_changed(self, mode):
        """Handle network view mode changes."""
        self.add_edge_action.setChecked(mode == EditMode.ADDING_EDGE)

    def on_network_modified(self):
        """Handle modifications to the network and update the window title."""
        self.modified = True
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

        # Add Species button
        add_species_action = toolbar.addAction("Add Species")
        add_species_action.triggered.connect(self.add_species_dialog)

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


    def add_species_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Species")
        layout = QVBoxLayout()

        # Add name input
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Species name:"))
        name_input = QLineEdit()
        name_layout.addWidget(name_input)
        layout.addLayout(name_layout)

        # Add species type selection
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Species type:"))
        input_radio = QRadioButton("Input")
        output_radio = QRadioButton("Output")
        output_radio.setChecked(True)  # Set Output (regular) as default

        # Add radio buttons to a button group
        type_group = QButtonGroup()
        type_group.addButton(input_radio)
        type_group.addButton(output_radio)

        type_layout.addWidget(input_radio)
        type_layout.addWidget(output_radio)
        layout.addLayout(type_layout)

        # Add delta input
        delta_layout = QHBoxLayout()
        delta_layout.addWidget(QLabel("Delta (degradation rate):"))
        delta_spin = QDoubleSpinBox()
        delta_spin.setRange(0, 1.0)
        delta_spin.setSingleStep(0.1)
        delta_spin.setValue(0.1)
        delta_layout.addWidget(delta_spin)
        layout.addLayout(delta_layout)

        # Toggle delta visibility based on species type
        def on_type_changed():
            delta_spin.setEnabled(output_radio.isChecked())
            if input_radio.isChecked():
                delta_spin.setValue(0)  # Set delta to 0 for input species

        input_radio.toggled.connect(on_type_changed)
        output_radio.toggled.connect(on_type_changed)

        # Add buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

        # Custom accept handler to validate input
        def handle_accept():
            name = name_input.text().strip()
            if not name:
                QMessageBox.warning(dialog, "Warning", "Please enter a species name.")
                return
            if name in self.network_view.grn.species_names:
                QMessageBox.warning(
                    dialog, "Warning", "A species with this name already exists."
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
            is_input = input_radio.isChecked()
            delta = delta_spin.value()

            # Add to GRN model
            if is_input:
                self.network_view.grn.add_input_species(name)
            else:
                self.network_view.grn.add_species(name, delta)

            self.network_view.grn_modified.emit()  # Signal that the network was modified

    def add_node_dialog(self):
        # If we're in edge mode, uncheck the edge button first
        if self.network_view.mode == EditMode.ADDING_EDGE:
            self.add_edge_action.setChecked(False)

        # Check if we have any species defined
        if not self.network_view.grn.species_names:
            QMessageBox.warning(
                self,
                "Warning",
                "Please add at least one species first using the 'Add Species' button."
            )
            return

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

        # Species selection
        species_layout = QHBoxLayout()
        species_layout.addWidget(QLabel("Select species:"))
        species_combo = QComboBox()
        species_combo.addItems(self.network_view.grn.species_names)
        species_layout.addWidget(species_combo)
        layout.addLayout(species_layout)


        # Alpha value input
        alpha_layout = QHBoxLayout()
        alpha_layout.addWidget(QLabel("Alpha:"))
        alpha_spin = QDoubleSpinBox()
        alpha_spin.setRange(0.0, 100.0)
        alpha_spin.setValue(10.0)
        alpha_spin.setSingleStep(0.1)
        alpha_layout.addWidget(alpha_spin)
        layout.addLayout(alpha_layout)

        # Logic type selection
        logic_layout = QHBoxLayout()
        logic_layout.addWidget(QLabel("Logic type:"))

        logic_and = QRadioButton("AND")
        logic_or = QRadioButton("OR")
        logic_and.setChecked(True)  # Set AND as default

        # Add logic radio buttons to a button group
        logic_group = QButtonGroup()
        logic_group.addButton(logic_and)
        logic_group.addButton(logic_or)

        logic_layout.addWidget(logic_and)
        logic_layout.addWidget(logic_or)
        layout.addLayout(logic_layout)

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
            # if name in self.network_view.nodes:
            #     QMessageBox.warning(
            #         dialog, "Warning", "A node with this name already exists."
            #     )
            #     return
            dialog.accept()

        button_box.accepted.connect(handle_accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        # Show dialog and process result
        if dialog.exec() == QDialog.DialogCode.Accepted:
            species_name = species_combo.currentText()
            display_name = name_input.text().strip()  # Get the display name
            logic_type = "and" if logic_and.isChecked() else "or"
            alpha = alpha_spin.value()

            self.network_view.start_add_node(species_name, logic_type, alpha, display_name)

    def edge_type_changed(self, index):
        """
        Update the edge type based on combo box selection.

        Args:
            `index` (int): Selected index (0 for activation, 1 for inhibition)
        """
        self.network_view.edge_type = (
            EdgeType.ACTIVATION if index == 0 else EdgeType.INHIBITION
        )

    def run_simulation(self):
        grn = self.network_view.grn
        sim_time = self.simulation_panel.time_spin.value()
        t_single = self.simulation_panel.t_single_spin.value()

        # set sim_time and t_single to int
        sim_time = int(sim_time)
        t_single = int(t_single)


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

        # this enables the simulation to run without a display
        import matplotlib
        matplotlib.use('Agg')

        # plots the network in a separate window
        # comment mathplotlib.use('Agg') to show the plot
        # grn.plot_network()

        # single simulation
        IN = np.zeros(len(grn.input_species_names))
        for i, species in enumerate(grn.input_species_names):
            IN[i] = sim_time

        T_single, Y_single = simulator.simulate_single(grn, IN)

        # show results in a separate window
        dialog_single = SingleSimulationDialog(T_single, Y_single, grn.species, self)
        dialog_single.exec()

        from itertools import product

        num_inputs = len(grn.input_species_names)
        levels = [0, sim_time]  # Possible levels for each input

        # Generate all combinations of input levels
        combinations = list(product(levels, repeat=num_inputs))

        print(sim_time)

        # Simulate the sequence with dynamic combinations
        T_sequence, Y_sequence = simulator.simulate_sequence(grn, combinations, t_single = t_single)

        # show results in a separate window
        dialog_sequence = SequenceSimulationDialog(T_sequence, Y_sequence, grn.species, self)
        dialog_sequence.exec()

        return

    def toggle_edge_mode(self, enabled):
        self.network_view.set_edge_mode(enabled)

    def new_network(self):
        # We do nothing if we are unable to save (potentially unsaved) changes
        if not self.maybe_save():
            return

        # Clear the current network
        self.network_view.clear()
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
                    "species": [],  # We'll rebuild this from current state
                    "input_species_names": self.network_view.grn.input_species_names,
                "genes": self.network_view.grn.genes,
                },
            }

            # Save nodes and rebuild species list
            species_data = {}  # Track species and their deltas
            for node in self.network_view.nodes.values():
                # Save node data

                network_data["nodes"].append({
                    "node_id": node.node_id,
                    "species_name": node.species_name,
                    "display_name": node.display_name,
                    "x": node.pos().x(),
                    "y": node.pos().y(),
                    "logic_type": str(node.logic_type),
                    "alpha": node.alpha
                })


                # Track species data
                if node.species_name not in species_data:
                    # Find species data from GRN
                    species_info = next(
                        (s for s in self.network_view.grn.species if s["name"] == node.species_name),
                        None
                    )
                    if species_info:
                        species_data[node.species_name] = species_info

            # Rebuild species list
            network_data["grn"]["species"] = list(species_data.values())

            # Save valid edges (those with existing node IDs)
            valid_node_ids = {node.node_id for node in self.network_view.nodes.values()}
            for edge in self.network_view.edges:
                if edge.source_node.node_id in valid_node_ids and edge.target_node.node_id in valid_node_ids:
                    network_data["edges"].append({
                        "source_id": edge.source_node.node_id,
                        "target_id": edge.target_node.node_id,
                        "source_species": edge.source_node.species_name,
                        "target_species": edge.target_node.species_name,
                        "type": edge.edge_type.value,
                        "kd": edge.kd,
                        "n": edge.n
                    })

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
        # We do nothing if we are unable to save (potentially unsaved) changes
        if not self.maybe_save():
            return

        file_name, _ = QFileDialog.getOpenFileName(
            self, "Open Network", "", "GReNMlin Files (*.grn);;All Files (*)"
        )
        if not file_name:
            return

        try:
            with open(file_name, "r") as f:
                network_data = json.load(f)

            # Clear current network
            self.network_view.clear()

            # Restore GRN state
            # First, restore all species with their deltas
            for species in network_data["grn"]["species"]:
                if species["name"] in network_data["grn"]["input_species_names"]:
                    self.network_view.grn.add_input_species(species["name"])
                else:
                    self.network_view.grn.add_species(species["name"], species.get("delta", 0.1))

            # Create nodes first and keep a mapping of node IDs
            node_map = {}
            for node_data in network_data["nodes"]:
                node = self.network_view.add_node(
                    species_name=node_data["species_name"],
                    logic_type=node_data.get("logic_type", "and"),  # Make sure this is a string
                    x=node_data["x"],
                    y=node_data["y"],
                    display_name=node_data.get("display_name")
                )
                node.alpha = node_data.get("alpha", 10.0)
                node_id = node_data.get("node_id", str(uuid.uuid4()))
                node.node_id = node_id
                node.logic_type = "and" if not isinstance(node_data.get("logic_type"), str) else node_data.get("logic_type")
                node_map[node_id] = node

            # Create edges using the node map, skipping invalid edges
            seen_edges = set()
            for edge_data in network_data["edges"]:
                source_node = node_map.get(edge_data.get("source_id"))
                target_node = node_map.get(edge_data.get("target_id"))

                if source_node and target_node:
                    edge_id = (source_node.node_id, target_node.node_id)
                    if edge_id not in seen_edges:
                        edge = NetworkEdge(
                            source_node,
                            target_node,
                            EdgeType(edge_data["type"]),
                            kd=edge_data.get("kd", 5.0),
                            n=edge_data.get("n", 2.0)
                        )
                        self.network_view.scene.addItem(edge)
                        self.network_view.edges.append(edge)
                        seen_edges.add(edge_id)

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
