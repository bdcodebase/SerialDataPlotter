# simple QT application to receive and display serial data, and send commands to a serial device
# assumes csv data with a delimiter, and a fixed number of plots
# uses pyqtgraph for plotting, pyqt5 for the GUI, and qasync for asyncio support in pyqt5
# uses Bleak for BLE support
#
# ToDo:
# - add custom filtering
# - add option and handling for time axis/time stamps
# won't do - add "save and restart" option in "config" tab
# done - BLE support
# done - add check for valid json in config file
# done - add compatibility function for older config files
#
# config file is a json file, see SDP_Config.py for structure

import SDP_Config as SDP
import SDP_BLE as BLE
from SDP_BLE import BLEScannerWindow

import asyncio
from qasync import QEventLoop, asyncSlot

#import pyqtgraph.Qt
from PyQt5 import QtCore, QtWidgets, QtSerialPort
import pyqtgraph as QtGraph
import pyqtgraph.Qt
import json
import os
import argparse

# command line arguments (overwrite options from config file)
parser = argparse.ArgumentParser(description='Liveplot from serial port')
parser.add_argument("--com", help="COM Port", default=None)
parser.add_argument("--plots", type=int, help="Number of Plots", default=None)
parser.add_argument("--samples", type=int, help="Number of samples per plot", default=None)
parser.add_argument("--config", help="config file", default=None)

args = parser.parse_args()
configlog = '[-PC-] Welcome! Starting session at ' + QtCore.QDateTime.currentDateTime().toString('yyyy-MM-dd hh:mm:ss')

if args.config is not None:
    try:    
        config = SDP.parseconfig(args.config) 
    except (json.JSONDecodeError, FileNotFoundError) as e:
        config = SDP.getdefaultconfig()
        configlog = configlog + f'\n[-PC-] Error reading config file "{args.config}": {e}. Using default config.'
else:
    config = SDP.getdefaultconfig()


class Widget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(Widget, self).__init__(parent)
        self.setWindowTitle(config['title'])
        # Set up the basic variables
        if args.com is not None: # command line argument has higher priority
            config['com'] = args.com
     
        if args.plots is not None:  # command line argument has higher priority
            config['plots'] = args.plots
       
        if args.samples is not None: # command line argument has higher priority
            config['samples'] = args.samples
         
        self.fastautoscale = True if config['autoscaleinterval'] > 0 else False

        self.ble = BLE.BLE()
        self.useBLE = False
        self.connected = False
        self.serial = None
        self.file = None

        self.idx = 0
        self.ax = []    # list of axes
        self.plt = []   # list of plots
        self.label_items = []  # list of label items for live values

        self.margin = 2.5

        self.data = []
        for i in range(config['plots']):
            self.data.append([0]*config['samples'])
            #self.data[i][config['samples']-1] = 1

        # Set up the user interface: Tab 1
        self.message_le = QtWidgets.QLineEdit(
            text="h",
            returnPressed=self.send)
        
        self.send_btn = QtWidgets.QPushButton(
            text="Send Command:",
            clicked=self.send
        )
        
        self.comport_le = QtWidgets.QLineEdit(config['com'])
        self.connect_btn = QtWidgets.QPushButton(
            text="Connect", 
            checkable=True,
            toggled=self.on_toggled
        )
        
        # Set up the user interface: Tab 3
        self.config_te = QtWidgets.QTextEdit(readOnly=True)

        # Set up the user interface: Tab 2
        self.output_te = QtWidgets.QTextEdit(readOnly=True)
        self.output_te.mouseDoubleClickEvent = self.clear
        self.output_te.setStyleSheet("font-size: 10pt; color: white; background-color: black; font-family: 'Courier New';")
        self.raw_cb = QtWidgets.QCheckBox('Show Raw Data')

        QtGraph.setConfigOption('background', config['background'])  # Set the default background color
        QtGraph.setConfigOption('foreground', config['foreground'])
        
        self.graph = QtGraph.GraphicsLayoutWidget()
        if config['framecolor'] is not None:
            self.graph.setStyleSheet(F"border: 5px solid {config['framecolor']};")

        font = QtGraph.QtGui.QFont()
        font.setPixelSize(12)
        
        for i in range(config['plots']):
            self.ax.append(self.graph.addPlot(row=i, col=0)) 
            self.plt.append(self.ax[i].plot(self.data[i][:]))
            self.ax[i].setLabel('left', f'<div style="font-size: 11pt">{config["channels"][i]["label"]}<\div>')
            self.ax[i].setXRange(0, config['samples'])
            
            self.plt[i].setPen(config['channels'][i]['color'], width=2)
            self.ax[i].showGrid(x=True, y=True)
            self.ax[i].getAxis('left').setStyle(tickFont = font)
            self.ax[i].getAxis('bottom').setStyle(tickFont = font)
            if i > 0:
                self.ax[i].setXLink(self.ax[0]) # link x-axis to first plot
            # Create a LabelItem for each plot
            self.label_items.append(pyqtgraph.LabelItem())
            self.label_items[i].setParentItem(self.ax[i].graphicsItem())
            self.label_items[i].anchor(itemPos=(0.9, 0.0), parentPos=(0.9, 0.0))


        self.ax[config['plots']-1].setLabel('bottom','Samples')

        # Create the main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        # Create the tab widget
        tab_widget = QtWidgets.QTabWidget()
        tab_widget.setMinimumSize(800, 600)
        tab_widget.setTabPosition(QtWidgets.QTabWidget.TabPosition.West)

        # First tab
        tab1 = QtWidgets.QWidget()
        tab1_layout = QtWidgets.QGridLayout(tab1)
        tab1_layout.addWidget(self.connect_btn, 0, 0)
        tab1_layout.addWidget(self.comport_le, 0, 1)
        # Add BLE scan button
        self.scan_ble_btn = QtWidgets.QPushButton(
            text="Scan BLE",
            clicked=self.open_ble_scanner
        )
        tab1_layout.addWidget(self.scan_ble_btn, 0, 2)

        #tab3_layout.addWidget(QtWidgets.QLabel("CSV Path:"), 0, 0)
        
        self.write_csv_btn = QtWidgets.QPushButton(
            text="Write to CSV",
            clicked=self.write_to_csv
        )

        self.csvpath_le = QtWidgets.QLineEdit(config['csvpath'])
        
        tab1_layout.addWidget(self.write_csv_btn, 0, 3)
        tab1_layout.addWidget(self.csvpath_le, 0, 4)

        tab1_layout.addWidget(self.graph, 1, 0, 1, 5)
        tab_widget.addTab(tab1, "Graph")

        # Second tab
        tab2 = QtWidgets.QWidget()
        tab2_layout = QtWidgets.QGridLayout(tab2)
        tab2_layout.addWidget(self.raw_cb, 0, 2)
        tab2_layout.addWidget(self.send_btn, 0, 0)
        tab2_layout.addWidget(self.message_le, 0, 1)
        tab2_layout.addWidget(self.output_te, 1, 0, 1, 2)
        self.output_te.setPlainText(configlog)
        tab_widget.addTab(tab2, "Terminal")

        # Third tab
        tab3 = QtWidgets.QWidget()
        tab3_layout = QtWidgets.QGridLayout(tab3)
        # # Add CSV path edit field
        # tab3_layout.addWidget(QtWidgets.QLabel("CSV Path:"), 0, 0)
        # self.csvpath_le = QtWidgets.QLineEdit(config['csvpath'])
        # tab3_layout.addWidget(self.csvpath_le, 0, 1)



        tab3_layout.addWidget(QtWidgets.QLabel("Config file:"),0,0)
        tab3_layout.addWidget(self.config_te,1,0)
        self.config_te.setPlainText(json.dumps(config, indent=4))

        tab_widget.addTab(tab3, "Config")

        # Add the tab widget to the main layout
        main_layout.addWidget(tab_widget)

        # Set the main layout as the layout for the main window
        self.setLayout(main_layout)
      
        # Set up the timer for updating the plot
        self.timer = QtCore.QTimer()
        self.timer.setInterval(config['refresh'])
        self.timer.timeout.connect(self.update_plot)
        self.timer.start()

    def open_ble_scanner(self):
        self.ble_scanner_window = BLEScannerWindow()
        self.ble_scanner_window.device_selected.connect(self.handle_device_selected)
        self.ble_scanner_window.show()

    def handle_device_selected(self, address):
        print(f"Selected device address: {address}")
        self.comport_le.setText(F"Address {address}")
        # Handle the selected device address (e.g., connect to the device)


    #@QtCore.pyqtSlot()
    def parseLine(self, line):
        values = line.split(config['delimiter'])
        try:
            for i in range(config['plots']):
                self.data[i][self.idx] = (float(values[i])-config['channels'][i]['offset'])*config['channels'][i]['scale_factor']
            if self.file is not None:
                for i in range(config['plots']-1):
                    self.file.write(F'{self.data[i][self.idx]};')
                self.file.write(F"{self.data[config['plots']-1][self.idx]}\n")  
            self.idx += 1         
        except: # either no float or not (enough) data: just throw to terminal log.
            self.output_te.append(line.rstrip('\r\n'))
        if self.idx >= config['samples']:
            self.idx = 0

    def receive(self,sender=None,data=None):
        if self.useBLE:
            #print(f'data: {data}, Type: {type(data)}')
            
            line = data.decode("utf-8") #str(data)#self.ble.client.recv()
            if self.raw_cb.isChecked():
                self.output_te.append(line.rstrip('\r\n'))
            self.parseLine(line)
        
        elif self.connected:
            while self.serial.canReadLine():
                line = self.serial.readLine().data().decode()
                if self.raw_cb.isChecked():
                    self.output_te.append(line.rstrip('\r\n'))
                self.parseLine(line)

 
    #@QtCore.pyqtSlot()
    @asyncSlot()
    async def send(self):
        if self.connected:
            if self.useBLE:
                self.ble.send_data(self.message_le.text().encode())
                self.output_te.append(F'[-PC-] => {self.message_le.text()}')
            else:
                self.serial.write(self.message_le.text().encode() + b'\r\n')
                self.output_te.append(F'[-PC-] => {self.message_le.text()}')
        else:
            self.output_te.append('[-PC-] Error: Not connected')

    @asyncSlot(bool)
    async def on_toggled(self,checked):
        #checked = self.connect_btn.isChecked()
        self.connect_btn.setText("Disconnect" if checked else "Connect")
        if checked:
            address = self.comport_le.text()
            if "Address" in address: # BLE
                address = address.replace("Address ", "")
                self.output_te.append(F"[-PC-] Connecting to {address}")
                await self.ble.connect_to_device(address,self.receive)
                #self.ble.client.start_notify(self.ble.rx_char_uuid, self.receive)
                self.connected = True
                self.useBLE = True
            else: # Serial
                self.serial = QtSerialPort.QSerialPort(
                    address,
                    baudRate=QtSerialPort.QSerialPort.Baud115200,
                    readyRead=self.receive
                )   
                config['com'] = address
                if not self.serial.isOpen():
                    if not self.serial.open(QtCore.QIODevice.ReadWrite):
                        self.connect_btn.setChecked(False)
                        self.output_te.append(F"[-PC-]  Failed to connect to {config['com']}")
                    else:
                        self.connected = True
        else:
            if self.useBLE:
                self.output_te.append(F"[-PC-] Disconnecting BLE")
                self.ble.disconnect()
                #self.ble.disconnect()
            else:
                self.serial.close()
            self.connected = False
       
    def write_to_csv(self):
        if self.file is None:
            #filename = config['csvpath'].replace('<home>', os.path.expanduser('~'))
            filename = self.csvpath_le.text().replace('<home>', os.path.expanduser('~')) \
                                             .replace('<date>', QtCore.QDateTime.currentDateTime().toString('yyyy-MM-dd')) \
                                             .replace('<time>', QtCore.QDateTime.currentDateTime().toString('hh-mm-ss')) \
                                             .replace('/', os.sep)  # for windows compatibility
            try:
                self.file =  open(filename, 'w')
                for i in range(config['plots']-1):
                    self.file.write(F'{config["channels"][i]["label"]};')
                self.file.write(F'{config["channels"][config["plots"]-1]["label"]}\n')
                self.output_te.append(F'[-PC-] Writing data to {filename}')
                self.write_csv_btn.setText('Stop writing')
                
            except:
                self.output_te.append(F'[-PC-] Error writing to {filename}')
                self.file = None
        else:
            self.file.close()
            self.file = None
            self.output_te.append(F'[-PC-] Stopped writing to CSV')
            self.write_csv_btn.setText('Write to CSV')


    def update_plot(self):
        if self.connected:
            for i in range(config['plots']):
                idx = self.idx - 1
                if idx < 0:
                    idx = config['samples'] - 1
                self.plt[i].setData(self.data[i][:])

                if config['channels'][i]['min'] is not None and config['channels'][i]['max'] is not None:
                    self.ax[i].setYRange(config['channels'][i]['min'], config['channels'][i]['max'])
                else:
                    if self.fastautoscale:
                        if idx>config['autoscaleinterval']:
                            newmin = min(self.data[i][idx-config['autoscaleinterval']:idx])
                            newmax = max(self.data[i][idx-config['autoscaleinterval']:idx])
                            if newmax == newmin:
                                newmax = newmax + 1
                            margin = (newmax - newmin) / self.margin
                            self.ax[i].setYRange(newmin - margin, newmax + margin)
                        else:
                            if idx > 0:
                                newmin = min(min(self.data[i][0:idx]),min(self.data[i][idx-config['autoscaleinterval']:]))
                                newmax = max(max(self.data[i][0:idx]),max(self.data[i][idx-config['autoscaleinterval']:]))
                                if newmax == newmin:
                                    newmax = newmax + 1
                                margin = (newmax-newmin)/self.margin
                                self.ax[i].setYRange(newmin-margin,newmax+margin)
                # Update the text item with the current value
                current_value = self.data[i][idx]
                self.label_items[i].setText(f'<div style="font-size: 11pt;color: {config["channels"][i]["color"]}">{current_value:.2f}<\div>')
                
    def clear(self, event):
        self.output_te.clear()


if __name__ == '__main__':
    import sys
    app = pyqtgraph.Qt.mkQApp() # see https://github.com/pyqtgraph/pyqtgraph/pull/1509, works for me
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    w = Widget()
    w.show()
    with loop:
        loop.run_forever()
    #sys.exit(app.exec_())