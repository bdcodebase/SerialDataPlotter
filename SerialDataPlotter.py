# simple QT application to receive and display serial data, and send commands to a serial device
# assumes csv data with a delimiter, and a fixed number of plots
# uses pyqtgraph for plotting, pyqt5 for the GUI, and qasync for asyncio support in pyqt5
# uses Bleak for BLE support
#
# ToDo:
# - add custom filtering
# - add option and handling for time axis/time stamps
# - add sending a command to device on connect
# - add sending a command to device when starting/stopping writing to csv
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


class Widget(QtWidgets.QWidget):
    def __init__(self, parent=None, config_file=None, com=None, plots=None, samples=None):
        super(Widget, self).__init__(parent)
        self.config = self.load_config(config_file)
        
        if com is not None:
            self.config['com'] = com
        if plots is not None:
            self.config['plots'] = plots
        if samples is not None:
            self.config['samples'] = samples    
        
        
        self.ble = BLE.BLE()
        self.useBLE = False
        self.connected = False
        self.serial = None
        self.file = None

        self.idx = 0
        self.fastautoscale = True if self.config['autoscaleinterval'] > 0 else False
        
        self.data = []
        for i in range(self.config['plots']):
            self.data.append([0]*self.config['samples'])
            #self.data[i][self.config['samples']-1] = 1

        self.InitUI()
        # Set up the timer for updating the plot
        self.timer = QtCore.QTimer()
        self.timer.setInterval(self.config['refresh'])
        self.timer.timeout.connect(self.update_plot)
        self.timer.start()

    def InitUI(self):
        self.setWindowTitle(self.config['title'])
        self.ax = []    # list of axes
        self.plt = []   # list of plots
        self.label_items = []  # list of label items for live values

        self.margin = 2.5
        self.message_le = QtWidgets.QLineEdit(
            text="h",
            returnPressed=self.send)
        
        self.send_btn = QtWidgets.QPushButton(
            text="Send Command:",
            clicked=self.send
        )
        
        self.comport_le = QtWidgets.QLineEdit(self.config['com'])
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

        QtGraph.setConfigOption('background', self.config['background'])  # Set the default background color
        QtGraph.setConfigOption('foreground', self.config['foreground'])
        
        self.graph = QtGraph.GraphicsLayoutWidget()
        if self.config['framecolor'] is not None:
            self.graph.setStyleSheet(F"border: 5px solid {self.config['framecolor']};")

        font = QtGraph.QtGui.QFont()
        font.setPixelSize(12)
        
        for i in range(self.config['plots']):
            self.ax.append(self.graph.addPlot(row=i, col=0)) 
            self.plt.append(self.ax[i].plot(self.data[i][:]))
            self.ax[i].setLabel('left', f'<div style="font-size: 11pt">{self.config["channels"][i]["label"]}<\div>')
            self.ax[i].setXRange(0, self.config['samples'])
            
            self.plt[i].setPen(self.config['channels'][i]['color'], width=2)
            self.ax[i].showGrid(x=True, y=True)
            self.ax[i].getAxis('left').setStyle(tickFont = font)
            self.ax[i].getAxis('bottom').setStyle(tickFont = font)
            if i > 0:
                self.ax[i].setXLink(self.ax[0]) # link x-axis to first plot
            # Create a LabelItem for each plot
            self.label_items.append(pyqtgraph.LabelItem())
            self.label_items[i].setParentItem(self.ax[i].graphicsItem())
            self.label_items[i].anchor(itemPos=(0.9, 0.0), parentPos=(0.9, 0.0))


        self.ax[self.config['plots']-1].setLabel('bottom','Samples')

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

        self.csvpath_le = QtWidgets.QLineEdit(self.config['csvpath'])
        
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
        self.output_te.setPlainText('[-PC-] Welcome! Starting session at ' + QtCore.QDateTime.currentDateTime().toString('yyyy-MM-dd hh:mm:ss'))
        
    
        tab_widget.addTab(tab2, "Terminal")

        # Third tab
        tab3 = QtWidgets.QWidget()
        tab3_layout = QtWidgets.QGridLayout(tab3)
        tab3_layout.addWidget(QtWidgets.QLabel("Config file:"),0,0)
        tab3_layout.addWidget(self.config_te,1,0)
        self.config_te.setPlainText(json.dumps(self.config, indent=4))

        tab_widget.addTab(tab3, "Config")

        # Add the tab widget to the main layout
        main_layout.addWidget(tab_widget)

        # Set the main layout as the layout for the main window
        self.setLayout(main_layout)


    def load_config(self, config_file):
        if config_file:
            try:
                return SDP.parseconfig(config_file)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                print(f'Error reading config file "{config_file}": {e}. Using default config.')
                return SDP.getdefaultconfig()
        else:
            return SDP.getdefaultconfig()

    def open_ble_scanner(self):
        self.ble_scanner_window = BLEScannerWindow()
        self.ble_scanner_window.device_selected.connect(self.handle_device_selected)
        self.ble_scanner_window.show()

    def handle_device_selected(self, address):
        print(f"Selected device address: {address}")
        self.comport_le.setText(F"Address {address}")
 

    #@QtCore.pyqtSlot()
    def parseLine(self, line):
        values = line.split(self.config['delimiter'])
        try:
            for i in range(self.config['plots']):
                self.data[i][self.idx] = (float(values[i])-self.config['channels'][i]['offset'])*self.config['channels'][i]['scale_factor']
            if self.file is not None:
                for i in range(self.config['plots']-1):
                    self.file.write(F'{self.data[i][self.idx]};')
                self.file.write(F"{self.data[self.config['plots']-1][self.idx]}\n")  
            self.idx += 1         
        except: # either no float or not (enough) data: just throw to terminal log.
            self.output_te.append(line.rstrip('\r\n'))
        if self.idx >= self.config['samples']:
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
    
    def sendCommand(self,command):
        command = command.replace('<date>', QtCore.QDateTime.currentDateTime().toString('yyyy-MM-dd'))\
                .replace('<time>', QtCore.QDateTime.currentDateTime().toString('hh-mm-ss')) 
        if self.connected:
            if self.useBLE:
                self.ble.send_data(command.encode())
                self.output_te.append(F'[-PC-] => {command}')
            else:
                self.serial.write(command.encode() + b'\r\n')
                self.output_te.append(F'[-PC-] => {command}')
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
                self.connected = True
                self.useBLE = True
            else: # Serial
                self.serial = QtSerialPort.QSerialPort(
                    address,
                    baudRate=QtSerialPort.QSerialPort.Baud115200,
                    readyRead=self.receive
                )   
                self.config['com'] = address
                if not self.serial.isOpen():
                    if not self.serial.open(QtCore.QIODevice.ReadWrite):
                        self.connect_btn.setChecked(False)
                        self.output_te.append(F"[-PC-]  Failed to connect to {self.config['com']}")
                    else:
                        self.connected = True
            if self.config['cmdconnect'] is not None:
                self.sendCommand(self.config['cmdconnect'])
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
            filename = self.csvpath_le.text().replace('<home>', os.path.expanduser('~')) \
                                             .replace('<date>', QtCore.QDateTime.currentDateTime().toString('yyyy-MM-dd')) \
                                             .replace('<time>', QtCore.QDateTime.currentDateTime().toString('hh-mm-ss')) \
                                             .replace('/', os.sep)  # for windows compatibility
            try:
                self.file =  open(filename, 'w')
                for i in range(self.config['plots']-1):
                    self.file.write(F'{self.config["channels"][i]["label"]};')
                self.file.write(F'{self.config["channels"][self.config["plots"]-1]["label"]}\n')
                self.output_te.append(F'[-PC-] Writing data to {filename}')
                self.write_csv_btn.setText('Stop writing')
                if self.config['cmdstartwritecsv'] is not None:        
                    self.sendCommand(self.config['cmdstartwritecsv'])
            except:
                self.output_te.append(F'[-PC-] Error writing to {filename}')
                self.file = None
        else:
            self.file.close()
            self.file = None
            self.output_te.append(F'[-PC-] Stopped writing to CSV')
            self.write_csv_btn.setText('Write to CSV')
            if self.config['cmdstopwritecsv'] is not None:
                self.sendCommand(self.config['cmdstopwritecsv'])


    def update_plot(self):
        if self.connected:
            for i in range(self.config['plots']):
                idx = self.idx - 1
                if idx < 0:
                    idx = self.config['samples'] - 1
                self.plt[i].setData(self.data[i][:])

                if self.config['channels'][i]['min'] is not None and self.config['channels'][i]['max'] is not None:
                    self.ax[i].setYRange(self.config['channels'][i]['min'], self.config['channels'][i]['max'])
                else:
                    if self.fastautoscale:
                        if idx>self.config['autoscaleinterval']:
                            newmin = min(self.data[i][idx-self.config['autoscaleinterval']:idx])
                            newmax = max(self.data[i][idx-self.config['autoscaleinterval']:idx])
                            if newmax == newmin:
                                newmax = newmax + 1
                            margin = (newmax - newmin) / self.margin
                            self.ax[i].setYRange(newmin - margin, newmax + margin)
                        else:
                            if idx > 0:
                                newmin = min(min(self.data[i][0:idx]),min(self.data[i][idx-self.config['autoscaleinterval']:]))
                                newmax = max(max(self.data[i][0:idx]),max(self.data[i][idx-self.config['autoscaleinterval']:]))
                                if newmax == newmin:
                                    newmax = newmax + 1
                                margin = (newmax-newmin)/self.margin
                                self.ax[i].setYRange(newmin-margin,newmax+margin)
                # Update the text item with the current value
                current_value = self.data[i][idx]
                self.label_items[i].setText(f'<div style="font-size: 11pt;color: {self.config["channels"][i]["color"]}">{current_value:.2f}<\div>')
                
    def clear(self, event):
        self.output_te.clear()
    
    def closeEvent(self, event):
        # Stop the timer
        self.timer.stop()
        
        # Close the serial port if open
        if self.serial and self.serial.isOpen():
            self.serial.close()
        
        # Disconnect BLE if connected
        if self.useBLE and self.connected:
            self.ble.disconnect()
        
        # Close the CSV file if open
        if self.file:
            self.file.close()
        
        # Accept the event to close the window
        event.accept()

if __name__ == '__main__':
    # command line arguments (overwrite options from config file)
    parser = argparse.ArgumentParser(description='Liveplot from serial port')
    parser.add_argument("--com", help="COM Port", default=None)
    parser.add_argument("--plots", type=int, help="Number of Plots", default=None)
    parser.add_argument("--samples", type=int, help="Number of samples per plot", default=None)
    parser.add_argument("--config", help="config file", default=None)

    args = parser.parse_args()
    app = pyqtgraph.Qt.mkQApp() # see https://github.com/pyqtgraph/pyqtgraph/pull/1509, works for me
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    w = Widget(config_file=args.config, com=args.com, plots=args.plots, samples=args.samples)
    w.show()
    with loop:
        loop.run_forever()
    #sys.exit(app.exec_())