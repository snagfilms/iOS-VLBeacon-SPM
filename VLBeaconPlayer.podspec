Pod::Spec.new do |s|
  s.name             = 'VLBeaconPlayer'
  s.version          = '1.0.0'
  s.summary          = 'VLBeacon SDK for beacon tracking and analytics'
  s.homepage         = 'https://github.com/snagfilms/iOS-VLBeacon-SPM'
  s.license          = { :type => 'MIT', :file => 'LICENSE' }
  s.authors          = { "VL Player" => "techsupport@viewlift.com" }
  
  s.source           = {
    :git => 'https://github.com/snagfilms/iOS-VLBeacon-SPM.git',
    :branch => 'Develop_Pod_Example'
  }
  
  s.ios.deployment_target = '14.0'
  s.tvos.deployment_target = '13.0'
  s.swift_versions = ['5.8', '5.9']  # Don't use 6.0
  
  s.source_files = 'Source/VLBeaconPlayer/**/*.{swift,h,m}'
  
  s.frameworks = 'Foundation'
  s.ios.frameworks = 'UIKit', 'CoreLocation'
  s.tvos.frameworks = 'UIKit'
  s.requires_arc = true
  s.module_name = 'VLBeaconPlayer'
  
  s.dependency 'VLPlayerLib'
    '
  # Disable concurrency checking completely
  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'SWIFT_STRICT_CONCURRENCY' => 'minimal',
    'SWIFT_VERSION' => '5.0',  # Force Swift 5 mode
    'OTHER_SWIFT_FLAGS' => '$(inherited) -Xfrontend -warn-concurrency -Xfrontend -enable-actor-data-race-checks'
  }
  
  # Also disable for user targets
  s.user_target_xcconfig = {
    'SWIFT_STRICT_CONCURRENCY' => 'minimal'
  }
end
