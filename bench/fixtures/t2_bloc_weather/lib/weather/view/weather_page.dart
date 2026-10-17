import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../repository/weather_repository.dart';
import '../../search/view/search_page.dart';
import '../../settings/view/settings_page.dart';
import '../../theme/cubit/theme_cubit.dart';
import '../bloc/weather_bloc.dart';
import '../widgets/weather_empty.dart';
import '../widgets/weather_error.dart';
import '../widgets/weather_loading.dart';
import '../widgets/weather_populated.dart';

class WeatherPage extends StatelessWidget {
  const WeatherPage({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (context) => WeatherBloc(context.read<WeatherRepository>()),
      child: BlocProvider(
        create: (context) =>
            ThemeCubit(weatherBloc: context.read<WeatherBloc>()),
        child: const WeatherView(),
      ),
    );
  }
}

class WeatherView extends StatelessWidget {
  const WeatherView({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () => Navigator.of(context).push(
              SettingsPage.route(context.read<WeatherBloc>()),
            ),
          ),
        ],
      ),
      body: Center(
        child: BlocBuilder<WeatherBloc, WeatherState>(
          builder: (context, state) {
            return switch (state.status) {
              WeatherStatus.initial => const WeatherEmpty(),
              WeatherStatus.loading => const WeatherLoading(),
              WeatherStatus.failure => const WeatherError(),
              WeatherStatus.success => WeatherPopulated(
                  weather: state.weather!,
                  units: state.temperatureUnits,
                  onRefresh: () {
                    final bloc = context.read<WeatherBloc>();
                    bloc.add(const WeatherRefreshed());
                    return bloc.stream.firstWhere(
                      (s) => s.status != WeatherStatus.loading,
                    );
                  },
                ),
            };
          },
        ),
      ),
      floatingActionButton: FloatingActionButton(
        child: const Icon(Icons.search, semanticLabel: 'Search'),
        onPressed: () async {
          final bloc = context.read<WeatherBloc>();
          final city = await Navigator.of(context).push(SearchPage.route());
          if (city != null) bloc.add(WeatherRequested(city));
        },
      ),
    );
  }
}
