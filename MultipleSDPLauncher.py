# Starts up to four instances of the SDP Launcher
# enables the user to write multiple CSV files with same starting time
# just provide the config file for each instance and press the button next to it
import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QLabel, QLineEdit
from SerialDataPlotter import Widget as SerialDataPlotterWidget
from qasync import QEventLoop
import asyncio
import pyqtgraph
import argparse

# Command line arguments for config file paths
parser = argparse.ArgumentParser(description='Multiple SDP Launcher')
parser.add_argument('--config1', help='Path to config file for instance 1', default=None)
parser.add_argument('--config2', help='Path to config file for instance 2', default=None)
parser.add_argument('--config3', help='Path to config file for instance 3', default=None)
parser.add_argument('--config4', help='Path to config file for instance 4', default=None)
args = parser.parse_args()



class MultipleSDPLauncher(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.instances = []

    def initUI(self):
        self.setWindowTitle('Multiple SDP Launcher')
        self.setGeometry(100, 100, 400, 300)
        layout = QVBoxLayout()

        self.config_edits = []
        self.config_buttons = []
        config_paths = [args.config1, args.config2, args.config3, args.config4]
        for i in range(4):
            h_layout = QHBoxLayout()
            
            button = QPushButton(f'Select Config {i+1}')
            button.clicked.connect(lambda _, idx=i: self.select_config(idx))
            self.config_buttons.append(button)

            edit = QLineEdit(config_paths[i] if config_paths[i] else f'Config {i+1}: Not selected')
            self.config_edits.append(edit)
            h_layout.addWidget(edit)

            h_layout.addWidget(button)

            layout.addLayout(h_layout)

        h_layout = QHBoxLayout()
        self.start_button = QPushButton('Start All Instances')
        self.start_button.clicked.connect(self.start_all_instances)
        h_layout.addWidget(self.start_button)

        self.stop_button = QPushButton('Stop All Instances')
        self.stop_button.clicked.connect(self.stop_all_instances)
        h_layout.addWidget(self.stop_button)

        layout.addLayout(h_layout)

        self.csv_button = QPushButton('Start/Stop Writing to CSV')
        self.csv_button.clicked.connect(self.toggle_csv_writing)
        layout.addWidget(self.csv_button)

        self.setLayout(layout)

    def select_config(self, idx):
        options = QFileDialog.Options()
        fileName, _ = QFileDialog.getOpenFileName(self, "Select Config File", "", "Config Files (*.cfg);;All Files (*)", options=options)
        if fileName:
            self.config_edits[idx].setText(fileName)
            self.config_buttons[idx].setProperty('config', fileName)

    def start_all_instances(self):
        for edit in self.config_edits:
            config = edit.text()
            if config and config != f'Config {self.config_edits.index(edit)+1}: Not selected':
                instance = SerialDataPlotterWidget(config_file=config)
                instance.show()
                self.instances.append(instance)

    def stop_all_instances(self):
        for instance in self.instances:
            instance.close()
        self.instances = []

    def toggle_csv_writing(self):
        for instance in self.instances:
            instance.write_to_csv()

if __name__ == '__main__':
    #app = QApplication(sys.argv)
    app = pyqtgraph.mkQApp()
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    launcher = MultipleSDPLauncher()
    launcher.show()
    with loop:
        loop.run_forever()