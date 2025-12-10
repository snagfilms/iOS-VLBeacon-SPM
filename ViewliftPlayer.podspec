Pod::Spec.new do |s|
  s.name             = 'ViewliftPlayer'
  s.version          = '1.0.0'
  s.summary          = 'React Native wrapper around ViewLift VLPlayer with beacon integration.'
  s.homepage         = 'https://github.com/snagfilms/iOS-VLBeacon-SPM'
  s.license          = { :type => 'MIT', :file => 'LICENSE' }
  s.authors          = { 'VL Player' => 'techsupport@viewlift.com' }

  # This is the wrapper library repo (adjust URL/branch if this is a different repo)
  s.source           = {
    :git => 'https://github.com/snagfilms/iOS-VLBeacon-SPM.git',
    :branch => 'Develop_Pod_Example'
  }

  s.ios.deployment_target  = '14.0'
  s.tvos.deployment_target = '13.0'
  s.swift_versions         = ['5.8', '5.9']

  # Your wrapper files
  s.source_files = 'Source/ViewliftPlayer/**/*.{swift,h,m}'

  # Core frameworks used by your code
  s.frameworks      = 'Foundation'
  s.ios.frameworks  = ['UIKit', 'CoreLocation']
  s.tvos.frameworks = ['UIKit']

  s.requires_arc = true
  s.module_name = 'ViewliftPlayer'   # keep this as your pod/module name

  # React Native bridge dependency
  s.dependency 'React-Core'

  # Player and beacon SDK dependencies used in RNPlayerModule.swift
  s.dependency 'VLPlayerLib'
  s.dependency 'VLBeaconLib'

  # Concurrency / Swift settings
  s.pod_target_xcconfig = {
    'DEFINES_MODULE'              => 'YES',
    'SWIFT_STRICT_CONCURRENCY'    => 'minimal',
    'SWIFT_VERSION'               => '5.0',
    'OTHER_SWIFT_FLAGS'           => '$(inherited) -Xfrontend -warn-concurrency -Xfrontend -enable-actor-data-race-checks'
  }

  s.user_target_xcconfig = {
    'SWIFT_STRICT_CONCURRENCY' => 'minimal'
  }
end
