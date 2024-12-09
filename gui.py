import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QLabel, QPushButton, QDockWidget,
                           QSpinBox, QDoubleSpinBox, QComboBox, QTabWidget)
from PyQt6.QtCore import Qt
import networkx as nx
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
from grn import GRN
import simulator

class NetworkCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super(NetworkCanvas, self).__init__(fig)
        self.setParent(parent)
        self.grn = GRN()  # Initialize GRN instance
        self.network = nx.DiGraph()
        self.update_network_from_grn()
        self.draw_network()

    def update_network_from_grn(self):
        self.network.clear()
        # Add all species as nodes
        for species in self.grn.species:
            self.network.add_node(species['name'])
        
        # Add edges from genes
        for gene in self.grn.genes:
            for product in gene['products']:
                for regulator in gene['regulators']:
                    self.network.add_edge(regulator['name'], product['name'])

    def draw_network(self):
        self.axes.clear()
        pos = nx.spring_layout(self.network)
        nx.draw(self.network, pos, ax=self.axes, with_labels=True, 
                node_color='lightblue', node_size=500, arrowsize=20)
        self.draw()

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

        # Create network visualization
        self.network_canvas = NetworkCanvas(self)
        layout.addWidget(self.network_canvas)

        # Create right panel with tabs
        right_panel = QTabWidget()
        
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
        add_edge_action = edit_menu.addAction("Add Edge")
        
        # View menu
        view_menu = menubar.addMenu("View")
        reset_view_action = view_menu.addAction("Reset View")

    def run_simulation(self):
        # Get current GRN from network canvas
        grn = self.network_canvas.grn
        
        # Get simulation time
        sim_time = self.simulation_panel.time_spin.value()
        
        # Run simulation using simulator module
        # TODO: Implement actual simulation call and visualization
        pass

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 