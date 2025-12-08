Pod::Spec.new do |s|
  s.name             = 'VLBeaconLib'
  s.version          = '1.0.0'
  s.summary          = 'VLBeacon SDK for beacon tracking and analytics'
  s.description      = <<-DESC
                       VLBeacon library for beacon tracking and analytics integration.
                       Supports both iOS and tvOS platforms.
                       DESC
  
  s.homepage         = 'https://github.com/snagfilms/iOS-VLBeacon-SPM'
  s.license          = { :type => 'MIT', :file => 'LICENSE' }
  s.authors          = { "VL Player" => "techsupport@viewlift.com" }
  
  s.source           = {
    :git => 'https://github.com/snagfilms/iOS-VLBeacon-SPM.git',
    :branch => 'Develop_Pod'
  }
  
  s.ios.deployment_target = '14.0'
  s.tvos.deployment_target = '13.0'
  s.swift_versions = ['5.8', '5.9', '6.0']
  
  # FIXED: Changed "Sources" to "Source" (singular)
  s.source_files = 'Source/VLBeaconLib/**/*.{swift,h,m}'
  
  # If you have resources in the Resources folder
  s.resources = 'Source/VLBeaconLib/Resources/**/*'
  
  s.frameworks = 'Foundation'
  s.ios.frameworks = 'UIKit', 'CoreLocation'
  s.tvos.frameworks = 'UIKit'
  s.requires_arc = true
  s.module_name = 'VLBeaconLib'
  
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES'
  }
end
