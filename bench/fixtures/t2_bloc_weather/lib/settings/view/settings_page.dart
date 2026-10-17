import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../weather/bloc/weather_bloc.dart';

class SettingsPage extends StatelessWidget {
  const SettingsPage._();

  static Route<void> route(WeatherBloc weatherBloc) {
    return MaterialPageRoute<void>(
      builder: (_) => BlocProvider.value(
        value: weatherBloc,
        child: const SettingsPage._(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        children: <Widget>[
          BlocBuilder<WeatherBloc, WeatherState>(
            buildWhen: (previous, current) =>
                previous.temperatureUnits != current.temperatureUnits,
            builder: (context, state) {
              return ListTile(
                title: const Text('Temperature Units'),
                isThreeLine: true,
                subtitle: const Text(
                  'Use metric measurements for temperature units.',
                ),
                trailing: Switch(
                  value: state.temperatureUnits == TemperatureUnits.celsius,
                  onChanged: (_) => context
                      .read<WeatherBloc>()
                      .add(const TemperatureUnitsToggled()),
                ),
              );
            },
          ),
        ],
      ),
    );
  }
}
