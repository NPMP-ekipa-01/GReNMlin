import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                           QHBoxLayout, QLabel, QPushButton, QDockWidget,
                           QSpinBox, QDoubleSpinBox, QComboBox, QTabWidget,
                           QGraphicsScene, QGraphicsView, QGraphicsItem,
                           QGraphicsEllipseItem, QGraphicsLineItem, QInputDialog, QFileDialog)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QPen, QBrush, QColor, QPainter
import numpy as np
from grn import GRN
import simulator
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import json

class NetworkNode(QGraphicsEllipseItem):
    def __init__(self, name, x, y, radius=20):
        super().__init__(0, 0, radius*2, radius*2)
        self.name = name
        self.setPos(x-radius, y-radius)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setBrush(QBrush(QColor(200, 220, 255)))
        self.setPen(QPen(Qt.GlobalColor.black))
        self.setAcceptHoverEvents(True)
        self.radius = radius

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setBrush(QBrush(QColor(255, 200, 200)))
            if isinstance(self.scene().views()[0], NetworkView):
                view = self.scene().views()[0]
                if view.edge_mode:
                    view.node_clicked(self)
                else:
                    super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setBrush(QBrush(QColor(200, 220, 255)))
        if not self.scene().views()[0].edge_mode:
            super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(QColor(220, 240, 255)))  # Highlight on hover
        if isinstance(self.scene().views()[0], NetworkView):
            view = self.scene().views()[0]
            if view.edge_mode and view.source_node and view.source_node != self:
                self.setBrush(QBrush(QColor(200, 255, 200)))  # Green highlight for valid target
                view.complete_edge(self)
                event.accept()
                return
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(QColor(200, 220, 255)))  # Reset color
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

class NetworkEdge(QGraphicsLineItem):
    def __init__(self, source_node, target_node, edge_type=1):
        super().__init__()
        self.source_node = source_node
        self.target_node = target_node
        self.edge_type = edge_type  # 1 for activation, -1 for inhibition
        self.setPen(QPen(QColor('blue' if edge_type == 1 else 'red'), 2))
        self.setZValue(-1)  # Draw edges behind nodes
        self.update_position()

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

class NetworkView(QGraphicsView):
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

        # Edge drawing state
        self.edge_mode = False
        self.source_node = None
        self.temp_line = None
        self.edge_type = 1  # 1 for activation, -1 for inhibition

    def add_node(self, name, x=None, y=None):
        if x is None:
            x = np.random.uniform(0, self.width())
        if y is None:
            y = np.random.uniform(0, self.height())

        node = NetworkNode(name, x, y)
        self.scene.addItem(node)
        self.nodes[name] = node

        # Add label
        text = self.scene.addText(name)
        text.setPos(x-10, y-10)
        return node

    def node_clicked(self, node):
        if self.source_node is None:
            # Start edge creation
            self.source_node = node
            self.temp_line = QGraphicsLineItem()
            self.temp_line.setPen(QPen(QColor('blue' if self.edge_type == 1 else 'red'), 2))
            self.scene.addItem(self.temp_line)

    def complete_edge(self, target_node):
        if self.source_node and self.source_node != target_node:
            edge = NetworkEdge(self.source_node, target_node, self.edge_type)
            self.scene.addItem(edge)
            self.edges.append(edge)

            # Update GRN
            regulator = {'name': self.source_node.name,
                        'type': self.edge_type,
                        'Kd': 5,  # Default values
                        'n': 2}
            product = {'name': target_node.name}
            self.grn.add_gene(10, [regulator], [product])

            # Clean up
            if self.temp_line:
                self.scene.removeItem(self.temp_line)
            self.source_node = None
            self.temp_line = None

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

            # Check if mouse is over a potential target node
            items = self.items(event.pos())
            for item in items:
                if isinstance(item, NetworkNode) and item != self.source_node:
                    item.setBrush(QBrush(QColor(200, 255, 200)))  # Green highlight
                    self.complete_edge(item)
                    return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # Cancel edge creation if released on empty space
        if event.button() == Qt.MouseButton.LeftButton and self.source_node:
            if self.temp_line:
                self.scene.removeItem(self.temp_line)
            self.source_node = None
            self.temp_line = None
            # Reset all node colors
            for node in self.nodes.values():
                node.setBrush(QBrush(QColor(200, 220, 255)))
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
        self.edge_mode = enabled
        # Update cursor to indicate mode
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
            # Disable node dragging in edge mode
            for node in self.nodes.values():
                node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            # Re-enable node dragging
            for node in self.nodes.values():
                node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            # Clean up any ongoing edge creation
            if self.temp_line:
                self.scene.removeItem(self.temp_line)
            self.source_node = None
            self.temp_line = None

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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GReNMlin - Gene Regulatory Network Modeling")
        self.setGeometry(100, 100, 1200, 800)

        # Ensure menu bar is visible with KDE global menu
        # Add these lines:
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
        name, ok = QInputDialog.getText(self, 'Add Node', 'Enter node name:')
        if ok and name:
            is_input = QInputDialog.getItem(self, 'Node Type', 'Select node type:', ['Regular', 'Input'], 0, False)[0] == 'Input'
            if is_input:
                self.network_view.grn.add_input_species(name)
            else:
                self.network_view.grn.add_species(name, 0.1)
            self.network_view.add_node(name)

    def edge_type_changed(self, index):
        # Update edge type in network view (0 = activation, 1 = inhibition)
        self.network_view.edge_type = 1 if index == 0 else -1

    def run_simulation(self):
        grn = self.network_view.grn
        sim_time = self.simulation_panel.time_spin.value()

        # Make sure we have some nodes
        if not grn.species:
            print("Please add some nodes to the network first.")
            return

        # Debug print
        print("\nNetwork state before simulation:")
        print("Species:", grn.species)
        print("Input species:", grn.input_species_names)
        print("Genes:", grn.genes)
        print()

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
            print(f"Simulation error: {str(e)}")
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

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
