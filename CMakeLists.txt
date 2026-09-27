# The package's native part: the program lungo generated from the proved model in ../formal,
# which the module capdag._formal loads. Built by scikit-build-core when the package is.
cmake_minimum_required(VERSION 3.20)
project(capdag LANGUAGES C)
add_subdirectory(src/capdag/_formal)
