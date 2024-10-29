import asyncio
from qasync import asyncSlot
from bleak import BleakScanner, BleakClient
import datetime

class BLE:
    def __init__(self):
        self.client = None
        self.nus_service_uuid = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
        self.rx_char_uuid = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
        self.tx_char_uuid = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

    @asyncSlot()
    async def scan_for_devices(self):
        devices = await BleakScanner.discover()
        for device in devices:
            print(f"Found device: {device.name}, {device.address}")
        return devices
    
    @asyncSlot(str)
    async def connect_to_device(self, address,receiver):
        self.client = BleakClient(address)
        try:
            await self.client.connect()
            print(f"Connected to {address}")
            await self.client.start_notify(self.rx_char_uuid, receiver)
        except Exception as e:
            print(f"Failed to connect: {e}")
            self.client = None

    @asyncSlot()
    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
            print("Disconnected")

    @asyncSlot(str)
    async def send_data(self, data):
        if self.client:
            await self.client.write_gatt_char(self.tx_char_uuid, data)
            print(f"Sent data: {data}")

    def notification_handler(self, sender, data):
        print(f"Received data: {data}")

# Example usage
async def main():
    ble = BLE()
    #print(f"{datetime.datetime.now()}: BLE Start scanning")
    devices = await ble.scan_for_devices()
    #print(f"{datetime.datetime.now()}: BLE Stop scanning")
    if devices:
        feather_device = next((device for device in devices if "Feather" in device.name), None)
        if feather_device:
            address = feather_device.address
            #print(f"{datetime.datetime.now()}: BLE found device with name containing 'Feather': {feather_device.name}, {address}")
        else:
            print("No device with name containing 'Feather' found")
            return
        #address = devices[0].address  # Replace with the desired device address
        await ble.connect_to_device(address)
        await asyncio.sleep(30)  # Keep the connection for 10 seconds
        await ble.disconnect()

if __name__ == "__main__":
    asyncio.run(main())