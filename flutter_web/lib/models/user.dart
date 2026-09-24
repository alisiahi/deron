class User {
  final String name;
  final String email;
  final String organization;
  final Map<String, dynamic>? rawInfo;

  User({
    required this.name,
    required this.email,
    required this.organization,
    this.rawInfo,
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      name: json['name'] ?? 'Unknown User',
      email: json['email'] ?? '',
      organization: json['organization'] ?? 'No Organization',
      rawInfo: json['raw_info'],
    );
  }
}
