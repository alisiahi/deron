import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_web/main.dart';

void main() {
  testWidgets('App load test', (WidgetTester tester) async {
    await tester.pumpWidget(const KiwiApp());
  });
}
