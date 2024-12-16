import json
import sys

import numpy as np
from matplotlib.figure import Figure
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPalette, QPen, QFont, QFontDatabase
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog,
                             QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                             QGraphicsEllipseItem, QGraphicsItem,
                             QGraphicsLineItem, QGraphicsScene, QGraphicsView,
                             QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                             QMessageBox, QPushButton, QRadioButton,
                             QTabWidget, QVBoxLayout, QWidget, QMenu, QTextEdit)

# Needs to be imported after Qt
from matplotlib.backends.backend_qt5agg import \
    FigureCanvasQTAgg as FigureCanvas

import simulator
from grn import GRN
from enum import Enum


class NetworkNode(QGraphicsEllipseItem):
    def __init__(self, name, x, y, radius=20, is_input=False):
        super().__init__(0, 0, radius*2, radius*2)
        self.name = name
        self.is_input = is_input  # Store whether this is an input node
        self.setPos(x-radius, y-radius)
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
                self.node_color = self.base_color.lighter(220)  # Even lighter for input nodes
            else:
                self.node_color = self.base_color.lighter(base_lightness)
        else:
            # In light mode, make nodes slightly darker
            if self.is_input:
                self.node_color = self.base_color.darker(120)  # Slightly darker for input nodes
            else:
                self.node_color = self.base_color.darker(110)
        
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
            if view.mode == EditMode.ADDING_EDGE and view.source_node and view.source_node != self:
                self.setBrush(QBrush(self.highlight_color))  # Use highlight color for valid target
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

class NodeLabel(QGraphicsItem):
    def __init__(self, text, parent_node):
        super().__init__(parent_node)
        self.text = text
        self.parent_node = parent_node
        
        # Connect to both palette and color scheme changes
        app = QApplication.instance()
        app.paletteChanged.connect(self.update_colors)
        app.styleHints().colorSchemeChanged.connect(self.update_colors)
        self.update_colors()

    def update_colors(self):
        self.text_color = QApplication.instance().palette().color(QPalette.ColorRole.Text)
        if self.scene():
            self.scene().update()

    def boundingRect(self):
        return QRectF(-20, -20, 40, 40)

    def paint(self, painter, option, widget):
        painter.setPen(QPen(self.text_color))
        painter.drawText(-10, -10, self.text)

class NetworkEdge(QGraphicsLineItem):
    def __init__(self, source_node, target_node, edge_type=1):
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
            edge_color = palette.color(QPalette.ColorRole.Link) if palette.color(QPalette.ColorRole.Link).isValid() \
                else palette.color(QPalette.ColorRole.Highlight)
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
    NORMAL = 0
    ADDING_NODE = 1
    ADDING_EDGE = 2

class NetworkView(QGraphicsView):
    # Add signals
    mode_changed = pyqtSignal(EditMode)
    status_message = pyqtSignal(str)
    
    def __init__(self, parent=None):
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
        """Handle state changes when mode changes"""
        # Clean up any temporary items
        if self.temp_line:
            self.scene.removeItem(self.temp_line)
            self.temp_line = None
        
        self.source_node = None
        
        # Update node dragging flags
        for node in self.nodes.values():
            node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, 
                        self.mode == EditMode.NORMAL)

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
                    f"Click to place {self.node_type_to_add.lower()} node '{self.node_name_to_add}' (Press Esc to cancel)")
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
        if self.mode == EditMode.ADDING_NODE and event.button() == Qt.MouseButton.LeftButton:
            # Get click position in scene coordinates
            scene_pos = self.mapToScene(event.pos())
            x, y = scene_pos.x(), scene_pos.y()

            # Add the node at click position
            if self.node_type_to_add == 'Input':
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
                self.temp_line.setLine(source_pos.x(), source_pos.y(), 
                                     source_pos.x(), source_pos.y())  # Initial line from node to itself
                self.temp_line.setPen(QPen(
                    QColor('blue' if self.edge_type == 1 else 'red'), 2))
                self.scene.addItem(self.temp_line)
                self.status_message.emit("Drag to target node to create edge")

    def complete_edge(self, target_node):
        """Complete edge creation and reset state"""
        if self.source_node and self.source_node != target_node:
            edge = NetworkEdge(self.source_node, target_node, self.edge_type)
            self.scene.addItem(edge)
            self.edges.append(edge)

            # Update GRN
            regulator = {
                'name': self.source_node.name,
                'type': self.edge_type,
                'Kd': 5,
                'n': 2
            }
            product = {'name': target_node.name}
            self.grn.add_gene(10, [regulator], [product])

            # Reset state
            self.mode = EditMode.NORMAL

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
                self.status_message.emit("Click and drag from source node to create edge")
            
            # Reset all node colors
            for node in self.nodes.values():
                node.setBrush(QBrush(node.node_color))  # Use the node's color update method
                
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
        dialog.setWindowTitle('Rename Node')
        layout = QVBoxLayout()
        
        # Add name input
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel('New name:'))
        name_input = QLineEdit()
        name_input.setText(node.name)
        name_layout.addWidget(name_input)
        layout.addLayout(name_layout)
        
        # Add buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        
        # Custom accept handler to validate name
        def handle_accept():
            new_name = name_input.text().strip()
            if not new_name:
                QMessageBox.warning(dialog, "Warning", "Please enter a node name.")
                return
            if new_name in self.nodes and new_name != node.name:
                QMessageBox.warning(dialog, "Warning", "A node with this name already exists.")
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
                if species['name'] == old_name:
                    species['name'] = new_name
                    break
            
            # Update input species names if necessary
            if old_name in self.grn.input_species_names:
                self.grn.input_species_names.remove(old_name)
                self.grn.input_species_names.append(new_name)
            
            # Update gene regulators and products
            for gene in self.grn.genes:
                for regulator in gene['regulators']:
                    if regulator['name'] == old_name:
                        regulator['name'] = new_name
                for product in gene['products']:
                    if product['name'] == old_name:
                        product['name'] = new_name
            
            # Force scene update
            self.scene.update()

    def delete_node(self, node):
        # Confirm deletion
        reply = QMessageBox.question(
            self.parent(),
            'Delete Node',
            f"Are you sure you want to delete node '{node.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
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
            self.grn.species = [s for s in self.grn.species if s['name'] != node.name]
            
            # Remove from input species if present
            if node.name in self.grn.input_species_names:
                self.grn.input_species_names.remove(node.name)
            
            # Remove genes where this node is a product
            self.grn.genes = [g for g in self.grn.genes 
                             if not any(p['name'] == node.name for p in g['products'])]
            
            # Remove this node as a regulator from remaining genes
            for gene in self.grn.genes:
                gene['regulators'] = [r for r in gene['regulators'] 
                                    if r['name'] != node.name]
                
                # If a gene has no regulators left, remove it
                if not gene['regulators']:
                    self.grn.genes.remove(gene)
            
            # Force scene update
            self.scene.update()

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

        ax.set_xlabel('Time')
        ax.set_ylabel('Concentration')
        ax.set_title('Species Concentrations over Time')
        ax.legend()

        self.setLayout(layout)

class NetworkStateDialog(QDialog):
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
        formatted_state += json.dumps(network_state['species'], indent=2)
        formatted_state += "\n\nInput Species:\n"
        formatted_state += json.dumps(network_state['input_species'], indent=2)
        formatted_state += "\n\nGenes:\n"
        formatted_state += json.dumps(network_state['genes'], indent=2)
        
        text_area.setText(formatted_state)
        layout.addWidget(text_area)

        # Add OK button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        self.setLayout(layout)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GReNMlin - Gene Regulatory Network Modeling")
        self.setGeometry(100, 100, 1200, 800)

        # Ensure menu bar is visible with KDE global menu
        if hasattr(self, 'menuBar'):
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

        # Track currently opened file
        self.current_file = None

        # Connect network view signals
        self.network_view.mode_changed.connect(self._handle_mode_change)
        self.network_view.status_message.connect(self.statusBar().showMessage)

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
        new_action.setShortcut("Ctrl+N")  # Add keyboard shortcut
        new_action.triggered.connect(self.new_network)

        open_action = file_menu.addAction("Open Network")
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.load_network)

        save_action = file_menu.addAction("Save Network")
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_network)

        save_as_action = file_menu.addAction("Save Network As ...")
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(lambda: self.save_network(save_as=True))

        # Edit menu
        edit_menu = menubar.addMenu("Edit")
        add_node_action = edit_menu.addAction("Add Node")
        add_node_action.triggered.connect(self.add_node_dialog)

        # View menu
        view_menu = menubar.addMenu("View")
        reset_view_action = view_menu.addAction("Reset View")
        reset_view_action.triggered.connect(self.network_view.resetTransform)

    def add_node_dialog(self):
        # If we're in edge mode, uncheck the edge button first
        if self.network_view.mode == EditMode.ADDING_EDGE:
            self.add_edge_action.setChecked(False)
            
        # Create a custom dialog with both name input and node type selection
        dialog = QDialog(self)
        dialog.setWindowTitle('Add Node')
        layout = QVBoxLayout()

        # Add name input
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel('Node name:'))
        name_input = QLineEdit()
        name_layout.addWidget(name_input)
        layout.addLayout(name_layout)

        # Add type selection with radio buttons
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel('Node type:'))
        
        # Create radio buttons
        regular_radio = QRadioButton('Regular')
        input_radio = QRadioButton('Input')
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
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        
        # Custom accept handler to validate name
        def handle_accept():
            name = name_input.text().strip()
            if not name:
                QMessageBox.warning(dialog, "Warning", "Please enter a node name.")
                return
            if name in self.network_view.nodes:
                QMessageBox.warning(dialog, "Warning", "A node with this name already exists.")
                return
            dialog.accept()
            
        button_box.accepted.connect(handle_accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)

        # Show dialog and process result
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_input.text().strip()
            node_type = 'Input' if input_radio.isChecked() else 'Regular'
            self.network_view.start_add_node(name, node_type)

    def edge_type_changed(self, index):
        # Update edge type in network view (0 = activation, 1 = inhibition)
        self.network_view.edge_type = 1 if index == 0 else -1

    def run_simulation(self):
        grn = self.network_view.grn
        sim_time = self.simulation_panel.time_spin.value()

        # Make sure we have some nodes
        if not grn.species:
            QMessageBox.warning(self, "Warning", "Please add some nodes to the network first.")
            return

        # Show debug dialog with network state
        network_state = {
            'species': grn.species,
            'input_species': grn.input_species_names,
            'genes': grn.genes
        }
        debug_dialog = NetworkStateDialog(network_state, self)
        debug_dialog.exec()

        # TODO: Fix implementation of simulation
        return

        # Get initial conditions and species names
        initial_state = []
        species_names = []
        for species in grn.species:
            species_names.append(species['name'])
            if species['name'] in grn.input_species_names:
                initial_state.append(10.0)  # Default input value
            else:
                initial_state.append(0.0)

        # Run simulation
        try:
            # First generate the model
            grn.generate_model()
            # Then simulate
            time_points, results = simulator.simulate_single(
                grn,
                initial_state,
                t_end=sim_time,
                plot_on=False
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
        """Create a new empty network"""
        reply = QMessageBox.question(self, 'New Network',
            "Are you sure you want to create a new network? Any unsaved changes will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            # Clear the current network
            self.network_view.scene.clear()
            self.network_view.nodes.clear()
            self.network_view.edges.clear()
            self.network_view.grn = GRN()
            self.current_file = None

    def save_network(self, save_as=False):
        """Save the current network to a file"""
        if self.current_file is None or save_as:
            file_name, _ = QFileDialog.getSaveFileName(
                self,
                "Save Network",
                "",
                "GReNMlin Files (*.grn);;All Files (*)"
            )
            if not file_name:
                return
            if not file_name.endswith('.grn'):
                file_name += '.grn'
            self.current_file = file_name

        try:
            # Create network data structure
            network_data = {
                'nodes': [],
                'edges': [],
                'grn': {
                    'species': self.network_view.grn.species,
                    'input_species_names': self.network_view.grn.input_species_names,
                    'genes': self.network_view.grn.genes
                }
            }

            # Save node positions
            for name, node in self.network_view.nodes.items():
                network_data['nodes'].append({
                    'name': name,
                    'x': node.pos().x(),
                    'y': node.pos().y(),
                    'is_input': name in self.network_view.grn.input_species_names
                })

            # Save edges
            for edge in self.network_view.edges:
                network_data['edges'].append({
                    'source': edge.source_node.name,
                    'target': edge.target_node.name,
                    'type': edge.edge_type
                })

            # Save to file
            with open(self.current_file, 'w') as f:
                json.dump(network_data, f, indent=2)

            self.statusBar().showMessage(f"Network saved to {self.current_file}", 3000)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save network: {str(e)}")
            print(f"Failed to save network: {str(e)}")

    def load_network(self):
        """Load a network from a file"""
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Open Network",
            "",
            "GReNMlin Files (*.grn);;All Files (*)"
        )

        if not file_name:
            return

        try:
            with open(file_name, 'r') as f:
                network_data = json.load(f)

            # Clear current network
            self.network_view.scene.clear()
            self.network_view.nodes.clear()
            self.network_view.edges.clear()
            self.network_view.grn = GRN()

            # Restore GRN state
            for species in network_data['grn']['species']:
                if species['name'] in network_data['grn']['input_species_names']:
                    self.network_view.grn.add_input_species(species['name'])
                else:
                    self.network_view.grn.add_species(species['name'], species['delta'])

            # Create nodes
            for node_data in network_data['nodes']:
                self.network_view.add_node(
                    node_data['name'],
                    node_data['x'],
                    node_data['y']
                )

            # Create edges
            for edge_data in network_data['edges']:
                source_node = self.network_view.nodes[edge_data['source']]
                target_node = self.network_view.nodes[edge_data['target']]
                edge = NetworkEdge(source_node, target_node, edge_data['type'])
                self.network_view.scene.addItem(edge)
                self.network_view.edges.append(edge)

            # Restore genes
            self.network_view.grn.genes = network_data['grn']['genes']

            self.current_file = file_name
            self.statusBar().showMessage(f"Network loaded from {file_name}", 3000)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load network: {str(e)}")

    def closeEvent(self, event):
        """Handle application closing"""
        if self.network_view.nodes:  # If there's a network loaded
            reply = QMessageBox.question(self, 'Close Application',
                "Do you want to save your changes before closing?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel)

            if reply == QMessageBox.StandardButton.Save:
                self.save_network()
                event.accept()
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                event.ignore()

    def _handle_mode_change(self, mode):
        """Handle network view mode changes"""
        # Update toolbar actions
        self.add_edge_action.setChecked(mode == EditMode.ADDING_EDGE)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
