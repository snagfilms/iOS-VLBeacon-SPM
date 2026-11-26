#!/usr/bin/env ruby
# add_to_targets.rb — add an existing file on disk to an Xcode project group and targets.
#
# Requires the xcodeproj gem (ships with CocoaPods):  gem install xcodeproj
#
# Usage:
#   ruby add_to_targets.rb <Project.xcodeproj> <file path relative to repo root> <Target A>[,<Target B>...] [--dry-run]
#
# * Creates missing groups along the file's folder path (groups mirror folders).
# * Adds the file to the Sources phase for code (.swift .m .mm .c .cpp), to Resources for
#   everything else (xib, storyboard, xcassets, json, strings, plist that is not Info.plist...).
#   Headers (.h) get a reference only.
# * Skips a target that already contains the file. Fails (exit 2) when a target name does not
#   exist — ask the developer which target to use instead of guessing.
# * If the folder is inside an Xcode 16 synchronized folder, prints that and does nothing.
require "xcodeproj"

proj_path, rel_file, target_csv, flag = ARGV
abort("usage: add_to_targets.rb <Project.xcodeproj> <relative/file/path> <Target[,Target]> [--dry-run]") unless proj_path && rel_file && target_csv
dry = flag == "--dry-run"
project = Xcodeproj::Project.open(proj_path)
repo_root = File.dirname(File.expand_path(proj_path))
abs_file = File.expand_path(rel_file, Dir.pwd)
abs_file = File.expand_path(rel_file, repo_root) unless File.exist?(abs_file)
abort("file not found on disk: #{rel_file}") unless File.exist?(abs_file)

if project.root_object.respond_to?(:file_system_synchronized_groups) || project.objects.any? { |o| o.isa == "PBXFileSystemSynchronizedRootGroup" }
  project.objects.select { |o| o.isa == "PBXFileSystemSynchronizedRootGroup" }.each do |g|
    gdir = File.expand_path(g.path.to_s, repo_root)
    if abs_file.start_with?(gdir + "/")
      puts "SYNCHRONIZED: #{rel_file} is inside synchronized folder '#{g.path}' — Xcode adds it automatically; nothing to do."
      exit 0
    end
  end
end

names = target_csv.split(",").map(&:strip)
targets = names.map do |n|
  t = project.targets.find { |x| x.name == n }
  unless t
    warn "TARGET NOT FOUND: '#{n}'. Available: #{project.targets.map(&:name).join(', ')}"
    exit 2
  end
  t
end

# find or create the group chain that mirrors the file's folder
rel_dir = File.dirname(abs_file).sub(repo_root + "/", "")
group = project.main_group
rel_dir.split("/").each do |part|
  next if part.empty? || part == "."
  child = group.children.find { |c| c.respond_to?(:display_name) && (c.path == part || c.display_name == part) && c.is_a?(Xcodeproj::Project::Object::PBXGroup) }
  if child.nil?
    puts "create group: #{part}"
    child = group.new_group(part, part) unless dry
  end
  group = child || group
end

ref = group.files.find { |f| f.real_path.to_s == abs_file }
if ref
  puts "file reference exists: #{rel_file}"
else
  puts "add file reference: #{rel_file}"
  ref = group.new_reference(abs_file) unless dry
end

ext = File.extname(abs_file).downcase
code = %w[.swift .m .mm .c .cpp].include?(ext)
header = ext == ".h"
targets.each do |t|
  if header
    puts "#{t.name}: header — reference only"
    next
  end
  phase = code ? t.source_build_phase : t.resources_build_phase
  if ref && phase.files_references.include?(ref)
    puts "#{t.name}: already in #{code ? 'Sources' : 'Resources'}"
  else
    puts "#{t.name}: add to #{code ? 'Sources' : 'Resources'}"
    phase.add_file_reference(ref, true) unless dry
  end
end
project.save unless dry
puts dry ? "DRY RUN — nothing saved" : "saved #{proj_path}"
