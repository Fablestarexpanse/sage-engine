# WIT packages

The `sage:core` WIT package is the public API that code fragments import. A component can only instantiate if the manifest declares every interface it imports. That check is the plugin seal.

Empty until M2. The package is versioned with semver. Engine N serves plugins built against WIT N-1 through adapters.
