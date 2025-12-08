Pod::Spec.new do |s|
  s.name             = 'VLBeacon'
  s.version          = '1.0.0'
  s.summary          = 'VLBeacon SDK'
  s.description      = <<-DESC
                       VLBeacon library for beacon tracking and analytics integration.
                       DESC
  
  s.homepage         = 'https://viewlift.com/'
  s.license          = { :type => 'MIT', :file => 'LICENSE' }
    s.authors      = { "VL Player" => "techsupport@viewlift.com" }
  s.source           = {
    :git => 'https://github.com/snagfilms/iOS-VLBeacon-SPM',
    :branch => 'Develop'
  }
  
  # Platform requirements
  s.ios.deployment_target = '14.0'
  s.tvos.deployment_target = '14.0'
  
  # Swift version
  s.swift_versions = ['5.0', '5.1', '5.2', '5.3', '5.4', '5.5', '5.6', '5.7', '5.8', '5.9', '6.0']
  
  # Source files - all Swift files under Source directory
  s.source_files = 'Source/**/*.{swift,h,m}'
  
  # Resources (if any)
  # s.resources = 'Source/Resources/**/*'
  
  # Public headers (if any)
  # s.public_header_files = 'Source/**/*.h'
  
  # Frameworks required
  s.frameworks = 'Foundation', 'UIKit', 'CoreLocation'
  
  # If you need system libraries
  # s.libraries = 'sqlite3', 'z'
  
  # Requires ARC
  s.requires_arc = true
  
  # If you have dependencies on other pods
  # s.dependency 'Alamofire', '~> 5.0'
  # s.dependency 'SwiftyJSON', '~> 5.0'
  
  # Module name (optional, defaults to pod name)
  s.module_name = 'VLBeaconLib'
  
  # Pod target xcconfig
  s.pod_target_xcconfig = {
    'SWIFT_VERSION' => '6.0',
    'DEFINES_MODULE' => 'YES'
  }
  
  # User target xcconfig (optional)
  # s.user_target_xcconfig = { 'EXCLUDED_ARCHS[sdk=iphonesimulator*]' => 'arm64' }
end

