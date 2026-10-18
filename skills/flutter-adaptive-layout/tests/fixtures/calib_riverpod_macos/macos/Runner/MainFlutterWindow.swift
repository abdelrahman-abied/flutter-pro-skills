import Cocoa
import FlutterMacOS

class MainFlutterWindow: NSWindow {
  override func awakeFromNib() {
    let controller = FlutterViewController()
    self.contentViewController = controller
    RegisterGeneratedPlugins(registry: controller)
    super.awakeFromNib()
  }
}
