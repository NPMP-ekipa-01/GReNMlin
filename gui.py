import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QLabel, QPushButton, QDockWidget,
                           QSpinBox, QDoubleSpinBox, QComboBox, QTabWidget,
                           QGraphicsScene, QGraphicsView, QGraphicsItem,
                           QGraphicsEllipseItem, QGraphicsLineItem, QInputDialog)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QBrush, QColor, QPainter
import numpy as np
from grn import GRN
import simulator

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
        
    def mousePressEvent(self, event):
        self.setBrush(QBrush(QColor(255, 200, 200)))
        super().mousePressEvent(event)
        
    def mouseReleaseEvent(self, event):
        self.setBrush(QBrush(QColor(200, 220, 255)))
        super().mouseReleaseEvent(event)

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

    def wheelEvent(self, event):
        # Zoom in/out with mouse wheel
        zoomInFactor = 1.25
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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GReNMlin - Gene Regulatory Network Modeling")
        self.setGeometry(100, 100, 1200, 800)

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
        
        # Connect signals
        self.simulation_panel.run_button.clicked.connect(self.run_simulation)

    def setup_menu(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        new_action = file_menu.addAction("New Network")
        open_action = file_menu.addAction("Open Network")
        save_action = file_menu.addAction("Save Network")
        
        # Edit menu
        edit_menu = menubar.addMenu("Edit")
        add_node_action = edit_menu.addAction("Add Node")
        add_node_action.triggered.connect(self.add_node_dialog)
        add_edge_action = edit_menu.addAction("Add Edge")
        
        # View menu
        view_menu = menubar.addMenu("View")
        reset_view_action = view_menu.addAction("Reset View")
        reset_view_action.triggered.connect(self.network_view.resetTransform)

    def add_node_dialog(self):
        name, ok = QInputDialog.getText(self, 'Add Node', 'Enter node name:')
        if ok and name:
            self.network_view.add_node(name)
            # Add to GRN
            self.network_view.grn.add_species(name, 0.1)  # Default degradation rate

    def run_simulation(self):
        grn = self.network_view.grn
        sim_time = self.simulation_panel.time_spin.value()
        # TODO: Implement actual simulation call and visualization
        pass

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 