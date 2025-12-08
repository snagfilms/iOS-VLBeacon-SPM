Pod::Spec.new do |s|
  s.name             = 'VLBeaconLib'
  s.version          = '1.0.0'  # Keep version for reference
  s.summary          = 'VLBeacon SDK for beacon tracking and analytics'
  s.description      = <<-DESC
                       VLBeacon library for beacon tracking and analytics integration.
                       Supports both iOS and tvOS platforms.
                       DESC
  
  s.homepage         = 'https://github.com/snagfilms/iOS-VLBeacon-SPM'
  s.license          = { :type => 'MIT', :file => 'LICENSE' }
  s.authors          = { "VL Player" => "techsupport@viewlift.com" }
  
  # Use branch instead of tag
  s.source           = {
    :git => 'https://github.com/snagfilms/iOS-VLBeacon-SPM.git',
    :branch => 'Develop_Pod'
  }
  
  # Platform requirements
  s.ios.deployment_target = '14.0'
  s.tvos.deployment_target = '13.0'
  
  # Swift version
  s.swift_versions = ['5.8', '5.9', '6.0']
  
  # Source files - matching SPM structure
  s.source_files = 'Sources/VLBeaconLib/**/*.{swift,h,m}'
  
  # Required frameworks
  s.frameworks = 'Foundation'
  
  # Platform-specific frameworks
  s.ios.frameworks = 'UIKit', 'CoreLocation'
  s.tvos.frameworks = 'UIKit'
  
  # Requires ARC
  s.requires_arc = true
  
  # Module name
  s.module_name = 'VLBeaconLib'
  
  # Pod target xcconfig
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES'
  }
end
