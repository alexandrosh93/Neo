import 'react-native-gesture-handler';
import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { StatusBar } from 'expo-status-bar';
import VisitListScreen from './src/screens/VisitListScreen';
import AddVisitScreen from './src/screens/AddVisitScreen';
import EditVisitScreen from './src/screens/EditVisitScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import { TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const Stack = createStackNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <StatusBar style="light" />
      <Stack.Navigator
        screenOptions={{
          headerStyle: { backgroundColor: '#2d6a4f' },
          headerTintColor: '#fff',
          headerTitleStyle: { fontWeight: '700' },
        }}
      >
        <Stack.Screen
          name="VisitList"
          component={VisitListScreen}
          options={({ navigation }) => ({
            title: "Neoclis Visit Recorder",
            headerRight: () => (
              <TouchableOpacity
                onPress={() => navigation.navigate('Settings')}
                style={{ marginRight: 16 }}
              >
                <Ionicons name="settings-outline" size={22} color="#fff" />
              </TouchableOpacity>
            ),
          })}
        />
        <Stack.Screen
          name="AddVisit"
          component={AddVisitScreen}
          options={{ title: 'Add Visit' }}
        />
        <Stack.Screen
          name="EditVisit"
          component={EditVisitScreen}
          options={{ title: 'Edit Visit' }}
        />
        <Stack.Screen
          name="Settings"
          component={SettingsScreen}
          options={{ title: 'Settings' }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
